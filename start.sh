#!/bin/bash
cd "."

echo
echo   🎀 赛博女友 - 启动中...
echo

if [ ! -f ".venv/bin/activate" ]; then
    echo   ❌ 未找到虚拟环境，请先运行: python install.py
    echo
    exit 1
fi

source .venv/bin/activate
python main.py "$@"
