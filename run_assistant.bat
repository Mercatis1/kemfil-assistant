@echo off
chcp 65001 >nul
rem Открывает окно чата с помощником. Ollama должна быть запущена.
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
".venv\Scripts\python.exe" "app\okno.py"
if errorlevel 1 pause