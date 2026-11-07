@echo off
rem Поднимает сервер на этом ПК и открывает публичный wss:// адрес через
rem Cloudflare Tunnel (бесплатно, без аккаунта). ПК должен быть включён.
setlocal
cd /d "%~dp0\.."

where cloudflared >nul 2>nul
if errorlevel 1 (
    echo cloudflared не найден.
    echo Установите его одной командой:
    echo     winget install --id Cloudflare.cloudflared
    echo или скачайте cloudflared-windows-amd64.exe с
    echo https://github.com/cloudflare/cloudflared/releases и положите в PATH.
    pause
    exit /b 1
)

if exist "dist\OmegaServer.exe" (
    start "Omega Server" "dist\OmegaServer.exe"
) else (
    start "Omega Server" python server.py
)

timeout /t 3 /nobreak >nul

echo.
echo Ниже будет адрес вида https://xxxx.trycloudflare.com
echo Клиенту указывайте: wss://xxxx.trycloudflare.com/ws
echo.
cloudflared tunnel --url http://localhost:8080
