@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Missing .venv. See WINDOWS-SETUP.md.
  pause
  exit /b 1
)
echo MediaMind: http://127.0.0.1:8765
echo Stop the server with Ctrl+C.
".venv\Scripts\python.exe" start.py %*
if errorlevel 1 pause
