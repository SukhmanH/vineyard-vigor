@echo off
rem Weekly vigor refresh — registered in Windows Task Scheduler.
rem Logs append to outputs\logs\weekly_update.log.
cd /d "%~dp0.."
if not exist outputs\logs mkdir outputs\logs
set PYTHONPATH=src
uv run python scripts\weekly_update.py >> outputs\logs\weekly_update.log 2>&1
