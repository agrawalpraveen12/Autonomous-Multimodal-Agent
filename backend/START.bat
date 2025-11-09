@echo off
cls
cd /d "%~dp0"

if not exist venv (
    python -m venv venv || py -m venv venv
)

call venv\Scripts\activate
pip install --upgrade pip
pip install -r requirements.txt

python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
