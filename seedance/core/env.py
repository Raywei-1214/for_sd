import os
from pathlib import Path

from seedance.core.runtime import get_runtime_root_dir

_ENV_LOADED = False
ENV_FILENAME = ".env.local"


def get_local_env_path() -> Path:
    return get_runtime_root_dir() / ENV_FILENAME


def read_local_env_values() -> dict[str, str]:
    env_path = get_local_env_path()
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def update_local_env_values(updates: dict[str, str | None]) -> None:
    # ================================
    # 统一管理 .env.local 的增量写入
    # 目的: 让 GUI 和手工配置复用同一条保存链路
    # 边界: 仅覆盖传入的键，未提及的键保持不变
    # ================================
    values = read_local_env_values()
    for key, value in updates.items():
        if value is None or not value.strip():
            values.pop(key, None)
            os.environ.pop(key, None)
            continue
        clean_value = value.strip()
        values[key] = clean_value
        os.environ[key] = clean_value

    env_path = get_local_env_path()
    lines = [f"{key}={values[key]}" for key in sorted(values)]
    content = "\n".join(lines) + ("\n" if lines else "")
    temp_path = env_path.with_name(f"{env_path.name}.tmp")
    temp_path.write_text(content, encoding="utf-8")
    os.replace(temp_path, env_path)


def load_local_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    env_path = get_local_env_path()
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
