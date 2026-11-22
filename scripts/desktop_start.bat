@echo off
rem Aesthetic Prism desktop launcher: detached uvicorn on 0.0.0.0:8010, then open page.
setlocal
set "ROOT=%~dp0.."
pushd "%ROOT%"

rem Start uvicorn detached (new window, survives this script exit).
start "AestheticPrism-serve" /min cmd /c "python -m uvicorn aesthetic_prism.serve.app:app --host 0.0.0.0 --port 8010 --app-dir src"

rem Wait for boot, then open the page in default browser.
timeout /t 3 /nobreak >nul
start "" "http://127.0.0.1:8010/"

popd
endlocal
exit /b 0
