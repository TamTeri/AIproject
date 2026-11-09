@echo off
rem Boot EventHub locally (needs Docker Desktop). Flags: -NoReset, -Stop. See scripts\run_local.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run_local.ps1" %*
pause
