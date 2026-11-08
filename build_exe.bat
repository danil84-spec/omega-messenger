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

rem Портативная версия «папкой» — надёжнее one-file (нет распаковки в %TEMP%)
python -m PyInstaller --noconfirm --clean OmegaClientDir.spec
if errorlevel 1 goto fail

python -m PyInstaller --noconfirm --clean OmegaServer.spec
if errorlevel 1 goto fail

echo.
echo Готово:
echo   dist\OmegaMessenger.exe   - клиент с меню запуска
echo   dist\OmegaClient.exe      - клиент одним файлом
echo   dist\OmegaClient\OmegaClient.exe - клиент папкой (надёжнее)
echo   dist\OmegaServer.exe      - сервер
echo.
echo Раздача: python deploy\make_client_package.py --dir wss://адрес/ws
pause
exit /b 0

:fail
echo.
echo Сборка не удалась, смотрите сообщения выше.
pause
exit /b 1
