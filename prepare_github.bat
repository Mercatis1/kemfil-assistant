@echo off
chcp 65001 >nul
rem Создаёт рядом папку «kemfil-assistant»: копию проекта без ключей, журналов и .venv.
rem Выкладывать на GitHub нужно именно её.
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
".venv\Scripts\python.exe" "app\dlya_github.py"
echo.
pause