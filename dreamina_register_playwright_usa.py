"""Seedance 2.0 主入口。

保留旧文件名，避免已有 bat/命令调用路径失效。
"""

from seedance.app.cli import main
from seedance.infra.browser_detector import find_chrome_browser


if __name__ == "__main__":
    main()
