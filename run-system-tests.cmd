@echo off
rem Double-click to run every EventHub system test (Selenium + Chrome).
rem Needs: Docker Desktop running, Google Chrome, and the .venv from README.md.
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (set PY=.venv\Scripts\python.exe) else (set PY=python)
%PY% scripts\run_system_tests.py --open %*
echo.
pause
