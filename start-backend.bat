@echo off
echo Starting RacePilot Backend...
cd /d "%~dp0"

if not exist ".venv" (
    echo ERROR: Virtual environment not found!
    echo Please run: python -m venv .venv
    echo Then: .venv\Scripts\activate
    echo Then: pip install -r requirements.txt
    pause
    exit /b 1
)

echo Activating virtual environment...
call .venv\Scripts\activate.bat

echo Starting backend on all network interfaces (0.0.0.0:8000)...
echo Your phone can now connect to: http://192.168.4.103:8000
echo.
echo Press Ctrl+C to stop the server
echo.

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
