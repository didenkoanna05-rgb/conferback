"""Вхід у систему, ролі та захист форм (блок БА, ФВ-21, ДВ-09)."""
import functools
import secrets

from flask import (Blueprint, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from . import refs
from .db import create_user, execute, get_db, query

bp = Blueprint("auth", __name__)

# Сторінки, доступні без входу
PUBLIC_ENDPOINTS = {"auth.login", "static", "service_worker", "manifest", "offline"}


def can(permission):
    user = g.get("user")
    return bool(user) and bool(user["roles"] & refs.PERMISSIONS[permission])


def require(permission):
    """Декоратор: дія доступна лише ролям, яким її дозволено."""
    def decorator(view):
        @functools.wraps(view)
        def wrapped(*args, **kwargs):
            if not can(permission):
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


def csrf_token():
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def load_user():
    g.user = None
    uid = session.get("user_id")
    if uid is None:
        return
    row = query("SELECT * FROM users WHERE id = ? AND is_active = 1", (uid,), one=True)
    if row is None:
        session.clear()
        return
    roles = {r["role"] for r in query("SELECT role FROM user_roles WHERE user_id = ?", (uid,))}
    g.user = {"id": row["id"], "username": row["username"], "full_name": row["full_name"], "roles": roles}


def guard():
    """Виконується перед кожним запитом: перевірка входу і токена форм."""
    load_user()
    if request.endpoint in PUBLIC_ENDPOINTS:
        if request.method == "POST":
            check_csrf()
        return None
    if g.user is None:
        if request.path.startswith("/api/"):
            return {"error": "login_required"}, 401
        return redirect(url_for("auth.login", next=request.full_path))
    if request.method == "POST":
        check_csrf()
    return None


def check_csrf():
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token")
    if not sent or not secrets.compare_digest(sent, session.get("csrf", "")):
        abort(400, "Форма застаріла. Оновіть сторінку і спробуйте ще раз.")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "")
        row = query("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,), one=True)
        if row and check_password_hash(row["password_hash"], password):
            session.clear()
            session["user_id"] = row["id"]
            session.permanent = True
            nxt = request.args.get("next", "")
            # Переходимо лише на сторінки цього ж сайту
            if not nxt.startswith("/") or nxt.startswith("//"):
                nxt = url_for("events.index")
            return redirect(nxt)
        flash("Неправильний логін або пароль.", "danger")
    return render_template("login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/users", methods=["GET", "POST"])
@require("users")
def users():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        password = request.form.get("password", "")
        roles = [r for r in request.form.getlist("roles") if r in refs.ROLES]
        if not username or not full_name or len(password) < 8 or not roles:
            flash("Заповніть усі поля: пароль від 8 символів і хоча б одна роль.", "danger")
        elif query("SELECT 1 FROM users WHERE username = ?", (username,), one=True):
            flash("Такий логін уже є.", "danger")
        else:
            create_user(username, full_name, password, roles)
            flash(f"Користувача {full_name} додано.", "success")
        return redirect(url_for("auth.users"))
    rows = query("SELECT * FROM users ORDER BY is_active DESC, full_name")
    roles = {}
    for r in query("SELECT user_id, role FROM user_roles"):
        roles.setdefault(r["user_id"], set()).add(r["role"])
    return render_template("users.html", users=rows, user_roles=roles)


@bp.route("/users/<int:uid>", methods=["POST"])
@require("users")
def user_update(uid):
    action = request.form.get("action")
    if uid == g.user["id"] and action == "toggle":
        flash("Не можна вимкнути власний обліковий запис.", "warning")
        return redirect(url_for("auth.users"))
    if action == "toggle":
        execute("UPDATE users SET is_active = 1 - is_active WHERE id = ?", (uid,))
    elif action == "roles":
        roles = [r for r in request.form.getlist("roles") if r in refs.ROLES]
        if uid == g.user["id"] and "head" not in roles:
            flash("Не можна забрати в себе роль керівника.", "warning")
            return redirect(url_for("auth.users"))
        db = get_db()
        db.execute("DELETE FROM user_roles WHERE user_id = ?", (uid,))
        db.executemany("INSERT INTO user_roles (user_id, role) VALUES (?, ?)", [(uid, r) for r in roles])
        db.commit()
    elif action == "password":
        password = request.form.get("password", "")
        if len(password) < 8:
            flash("Пароль має містити щонайменше 8 символів.", "danger")
            return redirect(url_for("auth.users"))
        execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(password), uid))
    flash("Зміни збережено.", "success")
    return redirect(url_for("auth.users"))


@bp.route("/roles")
def roles():
    return render_template("roles.html")
