@echo off
rem Загружает проект в ваш репозиторий GitHub (для деплоя на Render).
rem
rem   push-to-github.bat https://github.com/ВАШ_ЛОГИН/omega-messenger.git
rem
rem Репозиторий создайте заранее на github.com — пустой, без README.
rem При первом push откроется окно входа GitHub (или спросит токен).
setlocal
cd /d "%~dp0.."

if "%~1"=="" (
    echo Использование: push-to-github.bat https://github.com/ЛОГИН/omega-messenger.git
    pause
    exit /b 1
)

git remote remove origin >nul 2>nul
git remote add origin %1
git branch -M main
git push -u origin main

if errorlevel 1 (
    echo.
    echo Не удалось загрузить. Проверьте:
    echo  - репозиторий создан и пуст;
    echo  - логин/токен GitHub верный ^(токен: Settings - Developer settings - Personal access tokens, scope repo^).
) else (
    echo.
    echo Готово. Теперь Render: New -^> Web Service -^> выберите этот репозиторий.
)
pause
