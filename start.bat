@echo off
chcp 65001 >/dev/null 2>&1
title Cyber Girlfriend

echo.
echo   🎀 赛博女友 - 启动中...
echo.

if not exist ".venv\Scriptsctivate.bat" (
    echo   ❌ 未找到虚拟环境，请先运行: python install.py
    echo.
    pause
    exit /b 1
)

call .venv\Scriptsctivate.bat
python main.py %*
if errorlevel 1 (
    echo.
    echo   程序已退出
    pause
)
