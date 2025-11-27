from __future__ import annotations

from importlib import import_module
from typing import Dict

from ray_service.config import MODEL_REGISTRY, BaseModelConfig, LocalModelConfig
from ray_service.models.base import BaseModelRunner


def _load_class(path: str):
    module_name, class_name = path.split(":")
    module = import_module(module_name)
    return getattr(module, class_name)


class ModelRegistry:
    """Resolve model handlers by name."""

    def __init__(self, registry: Dict[str, BaseModelConfig]):
        self.registry = registry
        self._local_instances: Dict[str, BaseModelRunner] = {}

    def get(self, model_name: str) -> BaseModelConfig:
        if model_name not in self.registry:
            raise KeyError(f"model {model_name} not found")
        return self.registry[model_name]

    def get_local_runner(self, config: LocalModelConfig) -> BaseModelRunner:
        if config.name not in self._local_instances:
            cls = _load_class(config.implementation)
            self._local_instances[config.name] = cls(config.name, config.metadata)
        return self._local_instances[config.name]

