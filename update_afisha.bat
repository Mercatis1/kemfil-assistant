@echo off
chcp 65001 >nul
rem Собирает свежую афишу с kemfil.ru и обновляет индекс для поиска.
rem После этого закройте и снова откройте окно помощника.
cd /d "%~dp0"
set PYTHONDONTWRITEBYTECODE=1
".venv\Scripts\python.exe" "collector\sborshik.py" %*
if errorlevel 1 goto end
echo.
echo Обновляю индекс для поиска...
".venv\Scripts\python.exe" "collector\indeksator.py"
:end
echo.
pause