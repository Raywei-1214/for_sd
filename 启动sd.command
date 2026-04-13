#!/bin/zsh
set -euo pipefail

cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "未检测到 Python 3，请先安装 Python 3。"
  exit 1
fi

echo "使用解释器: ${PYTHON_CMD}"
echo "如果首次运行失败，请先执行:"
echo "  ${PYTHON_CMD} -m pip install -r requirements.txt"
echo "  ${PYTHON_CMD} -m playwright install chromium"
echo

"${PYTHON_CMD}" dreamina_register_playwright_usa.py --show-browser "$@"
