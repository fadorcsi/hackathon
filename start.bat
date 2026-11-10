@echo off
cd /d "%~dp0"
echo Installing / checking the parts the app needs...
py -m pip install --quiet -r requirements.txt
if exist key.txt (set /p ANTHROPIC_API_KEY=<key.txt)
echo.
echo Research to Posts is starting. Open http://localhost:8000 in your browser.
echo Keep this window open. Close it to stop the app.
echo.
start "" http://localhost:8000
py app.py
pause
