@echo off
setlocal
pushd "%~dp0"
"runtime\windows-x64\python.exe" -B install.py %*
set "PATCH_EXIT=%ERRORLEVEL%"
pause
popd
exit /b %PATCH_EXIT%
