@echo off
rem Публичный wss:// адрес для сервера OMEGA через Cloudflare Tunnel.
rem
rem   cloudflared-tunnel.bat          обычный запуск (QUIC)
rem   cloudflared-tunnel.bat http2    если провайдер блокирует UDP/7844
rem
rem Окно нужно держать открытым: закроете — адрес перестанет работать.
setlocal
cd /d "%~dp0.."

set "ROOT=%CD%"
set "CF=%ROOT%\tools\cloudflared.exe"
set "SERVER=%ROOT%\dist\OmegaServer.exe"

if not exist "%CF%" (
    echo Скачиваю cloudflared ^(~53 МБ^), это один раз...
    if not exist "%ROOT%\tools" mkdir "%ROOT%\tools"
    powershell -NoProfile -Command "Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile '%CF%' -UseBasicParsing"
    if not exist "%CF%" (
        echo Не удалось скачать cloudflared. Проверьте интернет.
        pause
        exit /b 1
    )
)

if not exist "%SERVER%" (
    echo Не найден %SERVER%
    echo Соберите exe: build_exe.bat, либо запустите python server.py вручную.
    pause
    exit /b 1
)

rem --- сервер на 8080, если ещё не запущен ---
netstat -ano | findstr ":8080" | findstr "LISTENING" >nul
if errorlevel 1 (
    echo Запускаю OmegaServer на порту 8080...
    start "Omega Server" /D "%ROOT%\dist" "%SERVER%" --port 8080
    timeout /t 3 /nobreak >nul
)

echo.
echo ============================================================
echo  Ниже появится адрес вида https://xxxx.trycloudflare.com
echo  Собеседникам давайте:  wss://xxxx.trycloudflare.com/ws
echo  Это окно не закрывайте, пока нужен сервер.
echo ============================================================
echo.

if /i "%~1"=="http2" (
    "%CF%" tunnel --url http://localhost:8080 --no-autoupdate --protocol http2
) else (
    "%CF%" tunnel --url http://localhost:8080 --no-autoupdate
)

echo.
echo Туннель остановлен.
pause
