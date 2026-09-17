@echo off
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if not errorlevel 1 (
  py -3 installer\launcher.py
) else (
  python installer\launcher.py
)
if errorlevel 1 pause
