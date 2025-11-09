@echo off
echo Creating virtual environment...
python -m venv venv
if %errorlevel% neq 0 (
    echo Python not found or venv creation failed. Trying 'py'...
    py -m venv venv
)

echo Installing dependencies...
call venv\Scripts\activate
pip install -r requirements.txt

echo Setup complete!
echo To run the app: python main.py
pause
