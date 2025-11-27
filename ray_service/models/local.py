from __future__ import annotations

import asyncio
from typing import Any, Dict

from .base import BaseModelRunner


class EchoModel(BaseModelRunner):
    """示例本地模型：原样返回 payload."""

    async def infer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        return {"model": self.name, "echo": payload}

