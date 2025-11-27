from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, Coroutine, List

import ray
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from ray import serve

from ray_service.config import (
    MODEL_REGISTRY,
    ExternalAPIConfig,
    LocalModelConfig,
    BaseModelConfig,
    get_settings,
)
from ray_service.heartbeat import HeartbeatReporter
from ray_service.logging_setup import configure_logging, get_logger
from ray_service.model_registry import ModelRegistry
from ray_service.models.external import ExternalAPIClient
from ray_service.task_queue import TaskQueue

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(__name__)


@ray.remote
class LocalModelWorker:
    def __init__(self, config: LocalModelConfig):
        from ray_service.model_registry import _load_class  # lazy import to avoid cycles

        cls = _load_class(config.implementation)
        self.runner = cls(config.name, config.metadata)

    async def infer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.runner.infer(payload)


@ray.remote
class ExternalModelWorker:
    def __init__(self, config: ExternalAPIConfig):
        self.client = ExternalAPIClient(
            name=config.name,
            endpoint=config.endpoint,
            method=config.method,
            headers=config.headers,
            timeout=config.timeout_seconds,
        )

    async def infer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        return await self.client.infer(payload)


app = FastAPI(title="Ray Algorithm Service")


@serve.deployment(
    # route_prefix="/",
    ray_actor_options={"num_cpus": 1},
    autoscaling_config=None,
)
@serve.ingress(app)
class ModelService:
    def __init__(self):
        self.settings = settings
        self.registry = ModelRegistry(MODEL_REGISTRY)
        self.task_queue = TaskQueue(self.settings.redis_url)
        self.limiters: Dict[str, asyncio.Semaphore] = {}
        self.local_workers: Dict[str, List[Any]] = {}
        self.external_workers: Dict[str, List[Any]] = {}
        self.worker_cursors: Dict[str, int] = {}
        self._background_tasks: set[asyncio.Task] = set()
        self._init_models()
        replica_ctx = serve.get_replica_context()
        worker_id = replica_ctx.replica_tag if replica_ctx else str(uuid.uuid4())
        self.heartbeat = HeartbeatReporter(
            worker_id=worker_id,
            redis_url=self.settings.redis_url,
            interval=self.settings.heartbeat_interval_seconds,
            ttl=self.settings.heartbeat_ttl_seconds,
        )
        self.heartbeat.start()

    def _init_models(self) -> None:
        for model_name, config in MODEL_REGISTRY.items():
            limiter_size = config.max_concurrency or self.settings.default_max_concurrency
            self.limiters[model_name] = asyncio.Semaphore(limiter_size)
            if isinstance(config, LocalModelConfig):
                replicas = max(1, config.num_workers)
                workers = [
                    LocalModelWorker.options(
                        num_cpus=config.num_cpus,
                        num_gpus=config.num_gpus,
                    ).remote(config)
                    for _ in range(replicas)
                ]
                self.local_workers[model_name] = workers
                self.worker_cursors[model_name] = 0
            elif isinstance(config, ExternalAPIConfig):
                replicas = max(1, config.num_workers)
                workers = [
                    ExternalModelWorker.options(
                        num_cpus=config.num_cpus,
                    ).remote(config)
                    for _ in range(replicas)
                ]
                self.external_workers[model_name] = workers
                self.worker_cursors[model_name] = 0

    def _pick_worker(self, model_name: str, pool: Dict[str, List[Any]]) -> Any:
        workers = pool[model_name]
        cursor = self.worker_cursors.get(model_name, 0)
        worker = workers[cursor]
        self.worker_cursors[model_name] = (cursor + 1) % len(workers)
        return worker

    async def _run_local(self, config: LocalModelConfig, payload: Dict[str, Any]) -> Dict[str, Any]:
        worker = self._pick_worker(config.name, self.local_workers)
        result_ref = worker.infer.remote(payload)
        return await result_ref

    async def _run_external(self, config: ExternalAPIConfig, payload: Dict[str, Any]) -> Dict[str, Any]:
        worker = self._pick_worker(config.name, self.external_workers)
        result_ref = worker.infer.remote(payload)
        return await result_ref

    async def _dispatch(self, config: BaseModelConfig, payload: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(config, LocalModelConfig):
            return await self._run_local(config, payload)
        if isinstance(config, ExternalAPIConfig):
            return await self._run_external(config, payload)
        raise ValueError(f"Unsupported model config: {config}")

    async def _process_task(self, task_id: str, config: BaseModelConfig, payload: Dict[str, Any]) -> Dict[str, Any]:
        limiter = self.limiters[config.name]
        await limiter.acquire()
        try:
            await self.task_queue.update_status(task_id, "running")
            result = await self._dispatch(config, payload)
            await self.task_queue.update_status(task_id, "completed", result)
            return result
        except Exception as exc:
            await self.task_queue.update_status(task_id, "failed", {"error": str(exc)})
            logger.exception("Task %s for model %s failed: %s", task_id, config.name, exc)
            raise
        finally:
            limiter.release()

    def _schedule_background(self, coro: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)

    @app.get("/healthz")
    async def healthz(self) -> Dict[str, str]:
        return {"status": "ok"}

    @app.post("/invoke/{model_name}")
    async def invoke(self, model_name: str, payload: Dict[str, Any]) -> JSONResponse:
        try:
            config = self.registry.get(model_name)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"model {model_name} not found")

        task_id = await self.task_queue.enqueue(model_name, payload)
        logger.info("Task %s queued for model %s", task_id, model_name)

        try:
            result = await self._process_task(task_id, config, payload)
            return JSONResponse({"task_id": task_id, "result": result})
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post("/tasks/{model_name}")
    async def submit_task(self, model_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            config = self.registry.get(model_name)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"model {model_name} not found")

        task_id = await self.task_queue.enqueue(model_name, payload)
        logger.info("Async task %s queued for model %s", task_id, model_name)
        self._schedule_background(self._process_task(task_id, config, payload))
        return {"task_id": task_id, "status": "queued"}

    @app.get("/tasks/{task_id}")
    async def get_task(self, task_id: str) -> Dict[str, Any]:
        data = await self.task_queue.get_task(task_id)
        if not data:
            raise HTTPException(status_code=404, detail=f"task {task_id} not found")
        return data


model_service = ModelService.bind()

