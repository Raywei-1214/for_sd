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
        logger.info("✓✓✓ 浏览器配置已保存")
    except Exception as exc:
        logger.warning(f"保存浏览器配置失败: {exc}")


def _windows_registry_paths() -> list[str]:
    if platform.system().lower() != "windows":
        return []

    try:
        import winreg
    except ImportError:
        return []

    registry_candidates = [
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"),
    ]
    discovered_paths: list[str] = []

    # ================================
    # 优先读取 Windows 注册表中的 Chrome 权威路径
    # 目的: 避免仅靠 where/常见目录导致漏检已安装 Chrome
    # 边界: 只读取 chrome.exe 默认值与 Path 字段，不写注册表
    # ================================
    for root_key, sub_key in registry_candidates:
        try:
            with winreg.OpenKey(root_key, sub_key) as registry_key:
                default_value, _ = winreg.QueryValueEx(registry_key, None)
                if default_value:
                    discovered_paths.append(str(default_value))
                try:
                    install_dir, _ = winreg.QueryValueEx(registry_key, "Path")
                    if install_dir:
                        discovered_paths.append(str(Path(install_dir) / "chrome.exe"))
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            continue
        except Exception as exc:
            logger.warning(f"读取 Chrome 注册表路径失败: {exc}")

    return discovered_paths


def _candidate_paths() -> list[str]:
    system_name = platform.system().lower()

    if system_name == "windows":
        return _windows_registry_paths() + [
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
        if not path_obj.is_file():
            return False

        file_size_ok = path_obj.stat().st_size > 1024 * 1024
        executable_ok = os.access(path_obj, os.X_OK)
        windows_binary_ok = platform.system().lower() == "windows" and path_obj.suffix.lower() == ".exe"
        return file_size_ok and (executable_ok or windows_binary_ok)
    except Exception:
        return False


def find_chrome_browser() -> Optional[str]:
    for path in _candidate_paths():
        if _is_valid_browser(path):
            logger.info(f"✓✓✓ 找到本地浏览器: {path}")
            return path

    for command in _command_candidates():
        resolved = shutil.which(command)
        if resolved and _is_valid_browser(resolved):
            logger.info(f"✓✓✓ 通过命令找到本地浏览器: {resolved}")
            return resolved

    if platform.system().lower() == "windows":
        try:
            creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            result = subprocess.run(
                ["where", "chrome"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=creation_flags,
            )
            if result.returncode == 0:
                chrome_path = result.stdout.strip().splitlines()[0]
                if _is_valid_browser(chrome_path):
                    logger.info(f"✓✓✓ 通过 where 找到本地浏览器: {chrome_path}")
                    return chrome_path
        except Exception as exc:
            logger.warning(f"通过 where 查找 Chrome 失败: {exc}")

    return None
