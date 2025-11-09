@echo off
echo ========================================
echo Starting Agentic AI Server...
echo ========================================
echo.

cd /d "%~dp0"

if not exist venv (
    echo ERROR: Virtual environment not found!
    echo Please run setup_env.bat first.
    pause
    exit
)

call venv\Scripts\activate
echo Virtual environment activated.
echo.
echo Starting server on http://localhost:8000
echo Press Ctrl+C to stop the server.
echo.
python -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
