import sys

from loguru import logger as _raw_loguru_logger

from spring_harness.core.config.settings import LOG_LEVEL


def set_log_level(level:str ='DEBUG'):
    _ = _raw_loguru_logger.remove()
    _ = _raw_loguru_logger.add(sys.stderr, level=level)

set_log_level(LOG_LEVEL)

logger = _raw_loguru_logger
