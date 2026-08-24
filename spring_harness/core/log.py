import sys

from loguru import logger as _raw_loguru_logger

from spring_harness.core.config.settings import log


def set_log_level(level: str = "DEBUG") -> None:
    _raw_loguru_logger.remove()
    _raw_loguru_logger.add(
        log.log_file,
        rotation="10 MB",
        retention="10 days",
        encoding="utf-8",
        level=level,
    )


set_log_level(log.log_level)

logger = _raw_loguru_logger
