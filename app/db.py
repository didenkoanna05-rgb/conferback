"""Доступ до бази даних SQLite через стандартний модуль sqlite3."""
import os
import sqlite3

import click
from flask import current_app, g
from werkzeug.security import generate_password_hash

from . import refs


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        # У SQLite перевірка зовнішніх ключів типово вимкнена
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql, args=()):
    db = get_db()
    cur = db.execute(sql, args)
    db.commit()
    return cur.lastrowid


def init_db():
    db = get_db()
    with current_app.open_resource("schema.sql") as f:
        db.executescript(f.read().decode("utf-8"))
    for name in refs.DEFAULT_COST_CATEGORIES:
        db.execute("INSERT OR IGNORE INTO cost_categories (name) VALUES (?)", (name,))
    for i, (name, hint) in enumerate(refs.DEFAULT_CRITERIA):
        db.execute(
            "INSERT OR IGNORE INTO criteria (name, hint, sort_order) VALUES (?, ?, ?)",
            (name, hint, i),
        )
    db.commit()


def create_user(username, full_name, password, roles):
    db = get_db()
    cur = db.execute(
        "INSERT INTO users (username, full_name, password_hash) VALUES (?, ?, ?)",
        (username, full_name, generate_password_hash(password)),
    )
    for role in roles:
        db.execute("INSERT INTO user_roles (user_id, role) VALUES (?, ?)", (cur.lastrowid, role))
    db.commit()
    return cur.lastrowid


@click.command("init-db")
def init_db_command():
    """Створити таблиці та базові довідники."""
    init_db()
    click.echo("Базу даних створено.")


@click.command("create-user")
@click.argument("username")
@click.argument("full_name")
@click.option("--password", prompt=True, hide_input=True)
@click.option("--roles", default="head,marketer,manager,rep", help="Ролі через кому")
def create_user_command(username, full_name, password, roles):
    """Додати користувача."""
    create_user(username, full_name, password, [r.strip() for r in roles.split(",") if r.strip()])
    click.echo(f"Користувача {username} створено.")


def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
    app.cli.add_command(create_user_command)
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)
    with app.app_context():
        init_db()
