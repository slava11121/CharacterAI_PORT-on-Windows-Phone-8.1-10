@echo off
setlocal
cd /d "%~dp0"
cd WorkingCore

if not exist "venv\Scripts\python.exe" (
  echo [!] Не найден venv\Scripts\python.exe
  echo     Сначала запусти Install.bat
  pause
  exit /b 1
)

echo [i] Запускаю login_once.py ...
"%CD%\venv\Scripts\python.exe" "%CD%\login_once.py"
echo.
if exist "state.json" (
  for %%I in ("state.json") do echo [ok] state.json создан (%%~zI bytes)
) else (
  echo [!] state.json не появился. Смотри ошибки выше.
)
pause
