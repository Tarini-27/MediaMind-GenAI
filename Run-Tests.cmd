@echo off
cd /d "%~dp0"
".venv\Scripts\python.exe" -m pytest tests -q -p no:cacheprovider %*
set "MEDIAMIND_TEST_EXIT=%ERRORLEVEL%"
pause
exit /b %MEDIAMIND_TEST_EXIT%
