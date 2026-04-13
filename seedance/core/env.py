import os
from pathlib import Path

from seedance.core.runtime import get_runtime_root_dir

_ENV_LOADED = False


def load_local_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_path = get_runtime_root_dir() / ".env.local"
    if not env_path.exists():
        _ENV_LOADED = True
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

    _ENV_LOADED = True


def get_env_value(key: str) -> str | None:
    load_local_env()
    return os.environ.get(key)
