#!/bin/bash
# 赛博伴侣 — 启动脚本 (macOS / Linux)
cd "$(dirname "$0")"

echo
echo "  🎀 赛博伴侣 v3.4 — 启动中..."
echo

if [ ! -f ".venv/bin/activate" ]; then
    echo "  ❌ 未找到虚拟环境，请先运行: python install.py"
    echo
    exit 1
fi

source .venv/bin/activate
python main.py "$@"
EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo
    echo "  程序已退出 (code: $EXIT_CODE)"
    echo
fi

exit $EXIT_CODE
