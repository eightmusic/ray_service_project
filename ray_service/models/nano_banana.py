from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Sequence

import aiohttp

from ray_service.config import get_settings
from ray_service.logging_setup import get_logger
from ray_service.models.base import BaseModelRunner

logger = get_logger(__name__)


class NanoBananaClient:
    def __init__(self, api_key: str, base_url: str = "https://api.apimart.ai/v1", timeout: int = 90):
        if not api_key:
            raise ValueError("NanoBanana API key is required")
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")

    async def create_task(self, image_urls: Sequence[str], prompt: str, size: str) -> str:
        payload = {
            "model": "gemini-2.5-flash-image-preview",
            "prompt": prompt,
            "size": size,
            "n": 1,
            "image_urls": list(image_urls),
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.base_url}/images/generations",
                json=payload,
                headers=self.headers,
                timeout=self.timeout,
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    raise RuntimeError(f"create_task failed: {response.status} -> {body}")
                result = await response.json()
        try:
            task_id = result["data"][0]["task_id"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected response: {result}") from exc
        return task_id

    async def get_result(self, task_id: str) -> Dict[str, Any]:
        url = f"{self.base_url}/tasks/{task_id}"
        start_time = asyncio.get_event_loop().time()
        async with aiohttp.ClientSession() as session:
            while True:
                elapsed = asyncio.get_event_loop().time() - start_time
                if elapsed > self.timeout:
                    raise TimeoutError(f"Polling task {task_id} timed out after {self.timeout}s")
                try:
                    async with session.get(url, headers=self.headers, timeout=self.timeout) as response:
                        if response.status == 429:
                            await asyncio.sleep(1)
                            continue
                        if response.status != 200:
                            body = await response.text()
                            raise RuntimeError(f"get_result failed: {response.status} -> {body}")
                        data = await response.json()
                except aiohttp.ClientError as exc:
                    raise RuntimeError(f"Network error: {exc}") from exc

                status = data.get("data", {}).get("status")
                if status == "completed":
                    try:
                        image_url = data["data"]["result"]["images"][0]["url"][0]
                        return {"status": status, "image_url": image_url, "raw": data}
                    except (KeyError, IndexError) as exc:
                        raise RuntimeError(f"Result format unexpected: {data}") from exc
                if status == "failed":
                    message = data.get("message", "unknown error")
                    raise RuntimeError(f"Task {task_id} failed: {message}")

                await asyncio.sleep(1)


class NanoBananaModel(BaseModelRunner):
    def __init__(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        super().__init__(name, metadata)
        settings = get_settings()
        self.default_size = self.metadata.get("default_size", "1:1")
        base_url = self.metadata.get("base_url", "https://api.apimart.ai/v1")
        timeout = int(self.metadata.get("timeout", 90))
        api_key = self.metadata.get("api_key") or settings.nanobanana_api_key
        self.client = NanoBananaClient(api_key=api_key, base_url=base_url, timeout=timeout)

    async def infer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        prompt = payload.get("prompt")
        image_urls = payload.get("image_urls") or []
        if isinstance(image_urls, str):
            image_urls = [image_urls]
        size = payload.get("size") or self.default_size or "1:1"
        if not prompt:
            raise ValueError("payload.prompt is required")
        if not image_urls:
            raise ValueError("payload.image_urls is required")

        task_id = await self.client.create_task(image_urls=image_urls, prompt=prompt, size=size)
        logger.info("NanoBanana task %s created", task_id)
        result = await self.client.get_result(task_id)
        return {"task_id": task_id, "result": result}

