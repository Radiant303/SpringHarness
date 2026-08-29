from pathlib import Path

from loguru import logger as _raw_loguru_logger

from spring_harness.core.config.settings import log

LOG_DIRECTORY = Path.home() / ".springharness"
LOG_FILE = LOG_DIRECTORY / "app.log"


def set_log_level(level: str = "DEBUG") -> None:
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True)
    _raw_loguru_logger.remove()
    _raw_loguru_logger.add(
        LOG_FILE,
        rotation="10 MB",
        retention="10 days",
        encoding="utf-8",
        level=level,
    )


set_log_level(log.log_level)

logger = _raw_loguru_logger
