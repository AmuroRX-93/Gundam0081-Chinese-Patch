@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 launcher.py
  exit /b
)
where python >nul 2>nul
if not errorlevel 1 (
  python launcher.py
  exit /b
)
echo 请从 python.org 安装 Python 3.9 或以上，再重试。
pause
