import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from seedance.core.config import BROWSER_CONFIG_FILE
from seedance.core.logger import get_logger

logger = get_logger()


def load_browser_config() -> dict:
    try:
        if BROWSER_CONFIG_FILE.exists():
            return json.loads(BROWSER_CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"加载浏览器配置失败: {exc}")

    return {}


def save_browser_config(config: dict) -> None:
    try:
        BROWSER_CONFIG_FILE.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print("✓✓✓ 浏览器配置已保存")
    except Exception as exc:
        logger.warning(f"保存浏览器配置失败: {exc}")


def _candidate_paths() -> list[str]:
    system_name = platform.system().lower()

    if system_name == "windows":
        return [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"D:\Program Files\Google\Chrome\Application\chrome.exe",
            r"D:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        ]

    if system_name == "darwin":
        home = str(Path.home())
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            f"{home}/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            f"{home}/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]

    return [
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ]


def _command_candidates() -> list[str]:
    system_name = platform.system().lower()

    if system_name == "windows":
        return ["chrome", "chrome.exe"]

    return ["google-chrome", "chromium", "chromium-browser"]


def _is_valid_browser(binary_path: str) -> bool:
    try:
        path_obj = Path(binary_path)
        return path_obj.is_file() and path_obj.stat().st_size > 1024 * 1024
    except Exception:
        return False


def find_chrome_browser() -> Optional[str]:
    for path in _candidate_paths():
        if _is_valid_browser(path):
            print(f"✓✓✓ 找到本地浏览器: {path}")
            return path

    for command in _command_candidates():
        resolved = shutil.which(command)
        if resolved and _is_valid_browser(resolved):
            print(f"✓✓✓ 通过命令找到本地浏览器: {resolved}")
            return resolved

    if platform.system().lower() == "windows":
        try:
            result = subprocess.run(
                ["where", "chrome"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                chrome_path = result.stdout.strip().splitlines()[0]
                if _is_valid_browser(chrome_path):
                    print(f"✓✓✓ 通过 where 找到本地浏览器: {chrome_path}")
                    return chrome_path
        except Exception as exc:
            logger.warning(f"通过 where 查找 Chrome 失败: {exc}")

    return None
