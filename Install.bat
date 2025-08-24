@echo off
setlocal
title CharacterAI - Install
cd /d "%~dp0"

set "CORE=%~dp0WorkingCore"
if not exist "%CORE%" mkdir "%CORE%"

if not exist "%CORE%\venv\Scripts\python.exe" (
  echo [*] Создаю venv...
  py -3 -m venv "%CORE%\venv" || (echo [X] venv fail & pause & exit /b 1)
)

call "%CORE%\venv\Scripts\activate.bat"
set "PY=%CORE%\venv\Scripts\python.exe"

echo [*] Ставлю пакеты...
"%PY%" -m pip install -U pip setuptools wheel
"%PY%" -m pip install "fastapi[standard]" uvicorn playwright pydantic

echo [*] Качаю встроенный Chromium (если ещё не скачан)...
"%PY%" -m playwright install chromium || (echo [X] playwright install fail & pause & exit /b 1)

echo [✓] Установка готова. Запусти Login.bat
pause
