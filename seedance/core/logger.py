import logging
from typing import Optional

from seedance.core.config import LOG_FILE

_LOGGER: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    global _LOGGER

    if _LOGGER is not None:
        return _LOGGER

    logger = logging.getLogger("seedance")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        stream_handler = logging.StreamHandler()
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

    _LOGGER = logger
    return logger
