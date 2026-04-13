import logging
from pathlib import Path
from typing import Optional

from seedance.core.config import LOG_FILE

_LOGGER: Optional[logging.Logger] = None


def _has_file_handler(logger: logging.Logger, target_file: Path) -> bool:
    target_path = str(target_file.resolve())
    for handler in logger.handlers:
        if isinstance(handler, logging.FileHandler):
            handler_path = getattr(handler, "baseFilename", None)
            if handler_path and str(Path(handler_path).resolve()) == target_path:
                return True
    return False


def _has_stream_handler(logger: logging.Logger) -> bool:
    for handler in logger.handlers:
        # ================================
        # 这里显式排除 FileHandler
        # 目的: 防止文件输出被误判成控制台输出
        # 边界: 只要已有纯 StreamHandler，就不重复添加
        # ================================
        if type(handler) is logging.StreamHandler:
            return True
    return False


def get_logger() -> logging.Logger:
    global _LOGGER

    if _LOGGER is not None:
        return _LOGGER

    logger = logging.getLogger("seedance")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ================================
    # 无论 logger 之前挂了什么 handler，都强制保证文件输出存在
    # 目的: 修复“界面有日志，但日志文件为空”的根因
    # 边界: 仅去重同一路径的 FileHandler，不干扰其他自定义 handler
    # ================================
    if not _has_file_handler(logger, LOG_FILE):
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    if not _has_stream_handler(logger):
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        logger.addHandler(stream_handler)

    _LOGGER = logger
    return logger
