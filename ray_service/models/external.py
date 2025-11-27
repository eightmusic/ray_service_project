from __future__ import annotations

from typing import Any, Dict

import httpx

from ray_service.logging_setup import get_logger

logger = get_logger(__name__)


class ExternalAPIClient:
    """Adapter to call remote inference endpoints."""

    def __init__(self, name: str, endpoint: str, method: str = "POST", headers: Dict[str, str] | None = None, timeout: float = 15.0):
        self.name = name
        self.endpoint = endpoint
        self.method = method.upper()
        self.headers = headers or {}
        self.timeout = timeout

    async def infer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            logger.info("Calling external model %s -> %s", self.name, self.endpoint)
            response = await client.request(
                self.method,
                self.endpoint,
                json=payload,
                headers=self.headers,
            )
            response.raise_for_status()
            return response.json()

