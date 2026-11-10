#!/bin/bash
# Запуск ConferBack на Linux або macOS:  bash start.sh
# Перший запуск: створює середовище, встановлює бібліотеки й демонстраційну базу.
set -e
cd "$(dirname "$0")"
if [ ! -x venv/bin/python ]; then
  echo "Створюю віртуальне середовище..."
  python3 -m venv venv
fi
echo "Встановлюю бібліотеки..."
venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt
if [ ! -f instance/conferback.sqlite ]; then
  echo "Створюю базу з демонстраційними даними..."
  venv/bin/python seed_demo.py --yes
fi
echo
echo "Сайт: http://127.0.0.1:5000   (логін head, пароль demo2026). Зупинити: Ctrl+C"
exec venv/bin/python -m flask --app wsgi run
