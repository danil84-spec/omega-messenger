@echo off
rem Пересборка пары exe в dist\ (нужен Python 3.10+ с pip).
setlocal
cd /d "%~dp0"

python -m pip install --upgrade pyinstaller customtkinter websockets aiohttp cryptography
if errorlevel 1 goto fail

python -m PyInstaller --noconfirm --clean OmegaMessenger.spec
if errorlevel 1 goto fail

python -m PyInstaller --noconfirm --clean OmegaClient.spec
if errorlevel 1 goto fail

python -m PyInstaller --noconfirm --clean OmegaServer.spec
if errorlevel 1 goto fail

echo.
echo Готово: dist\OmegaMessenger.exe, dist\OmegaClient.exe, dist\OmegaServer.exe
echo Держите OmegaMessenger.exe и OmegaServer.exe в одной папке.
echo Для раздачи людям собирайте release: OmegaClient.exe + ПРОЧТИ-МЕНЯ.txt.
pause
exit /b 0

:fail
echo.
echo Сборка не удалась, смотрите сообщения выше.
pause
exit /b 1
