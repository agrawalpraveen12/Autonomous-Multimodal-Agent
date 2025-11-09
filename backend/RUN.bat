@echo off
cls
echo ================================================
echo   AGENTIC AI - COMPLETE SETUP AND START
echo ================================================
echo.

cd /d "%~dp0"

REM Check Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ERROR: Python not found. Please install Python 3.9+
    pause
    exit /b 1
)

REM Create venv if not exists
if not exist venv (
    echo [1/4] Creating virtual environment...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo ERROR: Failed to create venv
        pause
        exit /b 1
    )
)

echo [2/4] Activating environment...
call venv\Scripts\activate

echo [3/4] Installing dependencies...
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
if %errorlevel% neq 0 (
    echo ERROR: Failed to install dependencies
    pause
    exit /b 1
)

echo.
echo [4/4] Starting server...
echo ================================================
echo.
echo   Server URL: http://localhost:8000
echo   Interface: http://localhost:8000/static/index.html
echo.
echo   Press Ctrl+C to stop
echo ================================================
echo.

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
