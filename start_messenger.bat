@echo off
rem Запуск мессенджера из папки, где лежит этот файл (раньше путь был жёстко прописан).
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
    echo Python не найден в PATH. Установите Python 3.10+ и повторите.
    pause
    exit /b 1
)

python Launcher.py %*
if errorlevel 1 (
    echo.
    echo Мессенджер завершился с ошибкой. Смотрите текст выше.
    pause
)
