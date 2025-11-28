import time
import ray
from ray import serve

from ray_service.config import get_settings
from ray_service.logging_setup import configure_logging, get_logger
from ray_service.service import model_service

logger = get_logger(__name__)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_file)
    if not ray.is_initialized():
        ray.init(namespace="ray-service", ignore_reinit_error=True)
    logger.info("Starting Ray Serve on %s:%s", settings.service_host, settings.service_port)
    serve.run(
        target=model_service,
        name="ray-model-service",
        route_prefix="/",
    )
    logger.info("Serving... Ctrl+C to exit")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()

