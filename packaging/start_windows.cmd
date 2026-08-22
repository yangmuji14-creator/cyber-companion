@echo off
setlocal
chcp 65001 >nul
set "BUNDLE=%~dp0"
if exist "%BUNDLE%runtime\python.exe" goto launch
echo 未找到便携运行环境: runtime\python.exe
echo 请重新下载完整的慕压缩包。
pause
exit /b 2

:launch
"%BUNDLE%runtime\python.exe" "%BUNDLE%app\portable_launcher.py"
set "EXIT_CODE=%ERRORLEVEL%"
if not "%EXIT_CODE%"=="0" pause
exit /b %EXIT_CODE%
