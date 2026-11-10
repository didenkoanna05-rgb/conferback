@echo off
rem Запуск ConferBack на Windows подвійним клацанням.
rem Перший запуск: створює середовище, встановлює бібліотеки й демонстраційну базу.
chcp 65001 >nul
cd /d "%~dp0"

set "PY=python"
where py >nul 2>nul && set "PY=py -3"

if not exist "venv\Scripts\python.exe" (
  echo Створюю віртуальне середовище...
  %PY% -m venv venv
  if errorlevel 1 goto nopython
)

echo Встановлюю бібліотеки...
"venv\Scripts\python.exe" -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 goto failed

if not exist "instance\conferback.sqlite" (
  echo Створюю базу з демонстраційними даними...
  "venv\Scripts\python.exe" seed_demo.py --yes
  if errorlevel 1 goto failed
)

echo.
echo Сайт: http://127.0.0.1:5000   (логін head, пароль demo2026)
echo Щоб зупинити сайт, закрийте це вікно.
echo.
start "" cmd /c "timeout /t 3 >nul & start http://127.0.0.1:5000"
"venv\Scripts\python.exe" -m flask --app wsgi run
pause
exit /b

:nopython
echo.
echo Python не знайдено. Встановіть Python 3.10 або новіший з https://www.python.org/downloads/
echo і під час встановлення позначте "Add python.exe to PATH". Потім запустіть цей файл знову.
pause
exit /b 1

:failed
echo.
echo Сталася помилка (див. повідомлення вище). Перевірте підключення до інтернету й спробуйте знову.
pause
exit /b 1
