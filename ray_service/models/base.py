from __future__ import annotations

import abc
from typing import Any, Dict, Optional


class BaseModelRunner(abc.ABC):
    """Base runner interface for any algorithm."""

    def __init__(self, name: str, metadata: Optional[Dict[str, Any]] = None):
        self.name = name
        self.metadata = metadata or {}

    @abc.abstractmethod
    async def infer(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Execute inference with the provided payload."""

