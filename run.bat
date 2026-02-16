@echo off
if not exist .env (
    echo Kopieer .env.example naar .env en vul je API token in.
    echo Voorbeeld: copy .env.example .env
    pause
    exit /b 1
)
if not exist venv (
    echo Virtuele omgeving aanmaken...
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt
) else (
    call venv\Scripts\activate.bat
)
echo Dashboard starten op http://localhost:5000
python app.py
