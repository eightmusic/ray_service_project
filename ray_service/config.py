from __future__ import annotations

from functools import lru_cache
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = Field("redis://localhost:6379/0", env="REDIS_URL")
    service_host: str = Field("0.0.0.0", env="SERVICE_HOST")
    service_port: int = Field(8000, env="SERVICE_PORT")
    heartbeat_interval_seconds: int = Field(10, env="HEARTBEAT_INTERVAL_SECONDS")
    heartbeat_ttl_seconds: int = Field(30, env="HEARTBEAT_TTL_SECONDS")
    default_max_concurrency: int = Field(4, env="DEFAULT_MAX_CONCURRENCY")
    log_level: str = Field("INFO", env="LOG_LEVEL")
    log_file: Optional[str] = Field(None, env="LOG_FILE")
    nanobanana_api_key: str = Field("", env="NANOBANANA_API_KEY")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


class BaseModelConfig(BaseModel):
    name: str
    type: Literal["local", "external"]
    max_concurrency: Optional[int] = None
    num_workers: int = 1
    num_cpus: float = 1.0
    num_gpus: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class LocalModelConfig(BaseModelConfig):
    type: Literal["local"] = "local"
    implementation: str  # python path to class


class ExternalAPIConfig(BaseModelConfig):
    type: Literal["external"] = "external"
    endpoint: str
    method: Literal["GET", "POST"] = "POST"
    headers: Dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = 15.0


MODEL_REGISTRY: Dict[str, BaseModelConfig] = {
    "local-echo": LocalModelConfig(
        name="local-echo",
        implementation="ray_service.models.local:EchoModel",
        max_concurrency=2,
        num_workers=1,
        num_cpus=0.5,
        metadata={"description": "示例：返回输入 payload"},
    ),
    "external-sentiment": ExternalAPIConfig(
        name="external-sentiment",
        endpoint="https://example.com/sentiment",
        method="POST",
        headers={"Authorization": "Bearer <token>"},
        timeout_seconds=20.0,
        num_workers=2,
        num_cpus=0.25,
        metadata={"description": "示例：转发到外部情感分析 API"},
    ),
    "nanobanana-image": LocalModelConfig(
        name="nanobanana-image",
        implementation="ray_service.models.nano_banana:NanoBananaModel",
        max_concurrency=2,
        num_workers=2,
        num_cpus=1.0,
        metadata={
            "description": "调用 NanoBanana API 进行图像生成",
            "default_size": "1:1",
        },
    ),
}


@lru_cache
def get_settings() -> Settings:
    return Settings()

