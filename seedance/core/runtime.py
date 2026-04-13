import sys
from pathlib import Path


def is_frozen_runtime() -> bool:
    return bool(getattr(sys, "frozen", False))


def get_runtime_root_dir() -> Path:
    # ================================
    # PyInstaller 打包后，所有运行时文件应跟随 exe 所在目录
    # 开发态则继续使用项目根目录
    # ================================
    if is_frozen_runtime():
        return Path(sys.executable).resolve().parent

    return Path(__file__).resolve().parents[2]
