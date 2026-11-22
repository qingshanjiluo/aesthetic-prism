@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONPATH=%~dp0src
set AP_ROOT=%~dp0
set NO_COLOR=
python -X utf8 launcher.py %*
set RC=%ERRORLEVEL%
echo.
pause
exit /b %RC%
