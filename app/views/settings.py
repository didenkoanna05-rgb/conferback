"""Довідники: критерії оцінки та категорії витрат додаються без зміни коду (ДВ-10)."""
import sqlite3

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..auth import require
from ..db import execute, query
from . import clean

bp = Blueprint("settings", __name__)

TABLES = {"criteria": "criteria", "categories": "cost_categories"}


@bp.route("/settings")
@require("settings")
def index():
    return render_template(
        "settings.html",
        criteria=query("SELECT * FROM criteria ORDER BY is_active DESC, sort_order, id"),
        categories=query("SELECT * FROM cost_categories ORDER BY is_active DESC, id"))


@bp.route("/settings/<kind>", methods=["POST"])
@require("settings")
def save(kind):
    table = TABLES.get(kind)
    if table is None:
        return redirect(url_for("settings.index"))
    action = request.form.get("action")
    item_id = request.form.get("id", type=int)
    name = clean(request.form.get("name"), 200)
    try:
        if action == "add" and name:
            if table == "criteria":
                order = query("SELECT COALESCE(MAX(sort_order), 0) + 1 AS n FROM criteria", one=True)["n"]
                execute("INSERT INTO criteria (name, hint, sort_order) VALUES (?, ?, ?)",
                        (name, clean(request.form.get("hint"), 300), order))
            else:
                execute("INSERT INTO cost_categories (name) VALUES (?)", (name,))
            flash(f"«{name}» додано.", "success")
        elif action == "rename" and item_id and name:
            execute(f"UPDATE {table} SET name = ? WHERE id = ?", (name, item_id))
            if table == "criteria":
                execute("UPDATE criteria SET hint = ? WHERE id = ?", (clean(request.form.get("hint"), 300), item_id))
            flash("Зміни збережено.", "success")
        elif action == "toggle" and item_id:
            execute(f"UPDATE {table} SET is_active = 1 - is_active WHERE id = ?", (item_id,))
            flash("Зміни збережено.", "success")
    except sqlite3.IntegrityError:
        flash("Така назва вже є.", "danger")
    return redirect(url_for("settings.index") + f"#{kind}")
