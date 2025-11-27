from __future__ import annotations

import asyncio
import time
from typing import Dict

import redis.asyncio as redis


class HeartbeatReporter:
    """Periodically update worker heartbeat keys in Redis."""

    def __init__(self, worker_id: str, redis_url: str, interval: int, ttl: int):
        self.worker_id = worker_id
        self.interval = interval
        self.ttl = ttl
        self._task: asyncio.Task | None = None
        self.client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def _run(self) -> None:
        key = f"ray_service:heartbeat:{self.worker_id}"
        while True:
            ts = str(time.time())
            await self.client.set(key, ts, ex=self.ttl)
            await asyncio.sleep(self.interval)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._run())


class HeartbeatMonitor:
    """Helper to fetch current heartbeat snapshots."""

    def __init__(self, redis_url: str):
        self.client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    async def snapshot(self) -> Dict[str, float]:
        keys = await self.client.keys("ray_service:heartbeat:*")
        data: Dict[str, float] = {}
        for key in keys:
            value = await self.client.get(key)
            if value:
                data[key.split(":")[-1]] = float(value)
        return data

