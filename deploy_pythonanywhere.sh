#!/bin/bash
# Встановлення і оновлення ConferBack на PythonAnywhere.
# Запуск у Bash-консолі PythonAnywhere:
#   curl -sL https://raw.githubusercontent.com/didenkoanna05-rgb/conferback/main/deploy_pythonanywhere.sh | bash
set -e
REPO=https://github.com/didenkoanna05-rgb/conferback.git
DIR="$HOME/conferback"

WSGI=$(ls /var/www/*_wsgi.py 2>/dev/null | head -1)
if [ -z "$WSGI" ]; then
  echo "Спочатку створіть вебзастосунок: вкладка Web -> Add a new web app -> Manual configuration -> Python 3.10."
  exit 1
fi

if [ -d "$DIR/.git" ]; then
  echo "Оновлюю код..."; git -C "$DIR" pull -q
else
  echo "Завантажую код..."; git clone -q "$REPO" "$DIR"
fi

echo "Встановлюю Flask..."
for v in 3.10 3.11 3.12 3.13; do
  if command -v "python$v" >/dev/null; then "python$v" -m pip install -q --user "Flask>=3.0,<4" 2>/dev/null || true; fi
done

cd "$DIR"
if [ ! -f instance/conferback.sqlite ]; then
  echo "Створюю базу з демонстраційними даними..."; python3 seed_demo.py --yes
fi

cat > "$WSGI" <<PY
import sys
sys.path.insert(0, "$DIR")
from wsgi import application  # noqa
PY
touch "$WSGI"
echo
echo "Готово! Сайт: https://$(basename "$WSGI" _wsgi.py | tr _ .)"
