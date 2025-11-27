from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, Optional

import redis.asyncio as redis


class TaskQueue:
    """Redis-backed task tracker."""

    TASK_STREAM = "ray_service:tasks"

    def __init__(self, redis_url: str):
        self.client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def enqueue(self, model_name: str, payload: Dict[str, Any]) -> str:
        task_id = str(uuid.uuid4())
        message = {
            "task_id": task_id,
            "model": model_name,
            "payload": json.dumps(payload),
            "status": "queued",
            "ts": str(time.time()),
        }
        await self.client.xadd(self.TASK_STREAM, message)
        await self.client.hset(f"ray_service:task:{task_id}", mapping=message)
        return task_id

    async def update_status(self, task_id: str, status: str, result: Optional[Dict[str, Any]] = None) -> None:
        mapping: Dict[str, Any] = {"status": status, "ts": str(time.time())}
        if result is not None:
            mapping["result"] = json.dumps(result)
        await self.client.hset(f"ray_service:task:{task_id}", mapping=mapping)

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        data = await self.client.hgetall(f"ray_service:task:{task_id}")
        if not data:
            return None
        decoded: Dict[str, Any] = dict(data)
        if "payload" in decoded:
            try:
                decoded["payload"] = json.loads(decoded["payload"])
            except json.JSONDecodeError:
                pass
        if "result" in decoded:
            try:
                decoded["result"] = json.loads(decoded["result"])
            except json.JSONDecodeError:
                pass
        return decoded

    async def close(self) -> None:
        await self.client.close()

