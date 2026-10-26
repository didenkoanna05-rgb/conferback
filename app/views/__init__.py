"""Спільні допоміжні функції для оброблювачів маршрутів."""
from datetime import date

from flask import abort

from ..db import query


def get_event(event_id):
    event = query("SELECT * FROM events WHERE id = ?", (event_id,), one=True)
    if event is None:
        abort(404)
    return event


def parse_amount(text):
    """Сума з форми: приймає «1 200,50» і «1200.5». Повертає None, якщо не число або менше нуля."""
    try:
        value = round(float(str(text).replace(" ", "").replace(" ", "").replace(",", ".")), 2)
    except ValueError:
        return None
    return value if value >= 0 else None


def parse_date(text):
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def parse_int(text, lo, hi):
    try:
        value = int(text)
    except (TypeError, ValueError):
        return None
    return value if lo <= value <= hi else None


def clean(text, limit=500):
    return (text or "").strip()[:limit] or None


def users_with_role(role):
    return query(
        "SELECT u.id, u.full_name FROM users u JOIN user_roles r ON r.user_id = u.id "
        "WHERE r.role = ? AND u.is_active = 1 ORDER BY u.full_name", (role,))
