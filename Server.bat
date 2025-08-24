@echo off
setlocal
title CharacterAI - Server
cd /d "%~dp0"

set "CORE=%~dp0WorkingCore"
if not exist "%CORE%\venv\Scripts\python.exe" ( echo [!] Сначала Install.bat & pause & exit /b 1 )
if not exist "%CORE%\state.json" ( echo [!] Нет state.json. Запусти Login.bat & pause & exit /b 1 )

call "%CORE%\venv\Scripts\activate.bat"
set "PY=%CORE%\venv\Scripts\python.exe"

REM откроем порт молча (не критично)
netsh advfirewall firewall add rule name="CharacterAI Proxy 8000" dir=in action=allow protocol=TCP localport=8000 >nul 2>&1

pushd "%CORE%"
echo [*] Сервер: http://localhost:8000   (с телефона: http://IP_ПК:8000)
echo [*] Документация: http://localhost:8000/docs
"%PY%" -m uvicorn server:app --host 0.0.0.0 --port 8000 --http h11 --h11-max-incomplete-event-size 10485760
popd

pause
