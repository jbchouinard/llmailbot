import sys
from enum import StrEnum

from loguru import logger


class LogLevel(StrEnum):
    TRACE = "TRACE"
    DEBUG = "DEBUG"
    INFO = "INFO"
    SUCCESS = "SUCCESS"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


def setup_logging(log_file=None, log_level: str | LogLevel = LogLevel.INFO):
    log_level = LogLevel(log_level.upper())
    logger.remove()
    logger.add(log_file or sys.stderr, level=log_level.value)
