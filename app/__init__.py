"""ConferBack — інформаційна система підтримки лідогенерації на конференціях і виставках."""
import json
import os
import secrets
from datetime import date, datetime, timedelta

from flask import Flask, g, render_template, send_from_directory, url_for

from . import auth, calc, db, formulas, refs, stats

MONTHS = ["січ", "лют", "бер", "квіт", "трав", "черв", "лип", "серп", "вер", "жовт", "лист", "груд"]


def _load_secret(instance_path):
    path = os.path.join(instance_path, "secret_key")
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(secrets.token_hex(32))
    with open(path) as f:
        return f.read().strip()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    os.makedirs(app.instance_path, exist_ok=True)
    app.config.update(
        DATABASE=os.path.join(app.instance_path, "conferback.sqlite"),
        PERMANENT_SESSION_LIFETIME=timedelta(days=14),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        app.config.update(test_config)
    # Підказка з демонстраційними логінами на сторінці входу (файл створює seed_demo.py)
    demo_file = os.path.join(app.instance_path, "demo.json")
    if os.path.exists(demo_file) and "DEMO_LOGINS" not in app.config:
        with open(demo_file, encoding="utf-8") as f:
            demo = json.load(f)
        app.config["DEMO_LOGINS"] = demo["logins"]
        app.config["DEMO_PASSWORD"] = demo["password"]
    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or _load_secret(app.instance_path)

    db.init_app(app)
    app.before_request(auth.guard)

    from .views import analytics, events, leads, settings, targets
    for module in (auth, events, targets, leads, analytics, settings):
        app.register_blueprint(module.bp)

    _register_helpers(app)

    @app.route("/sw.js")
    def service_worker():
        # Службовий сценарій має лежати в корені, щоб керувати всіма сторінками
        resp = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @app.route("/manifest.webmanifest")
    def manifest():
        return send_from_directory(app.static_folder, "manifest.webmanifest",
                                   mimetype="application/manifest+json")

    @app.route("/offline")
    def offline():
        return render_template("offline.html")

    for code, title in ((403, "Ця дія недоступна для вашої ролі"),
                        (404, "Сторінку не знайдено"),
                        (400, "Некоректний запит")):
        app.register_error_handler(code, _error_handler(code, title))
    return app


def _error_handler(code, title):
    def handler(err):
        detail = getattr(err, "description", "") if code == 400 else ""
        return render_template("error.html", code=code, title=title, detail=detail), code
    return handler


def _register_helpers(app):
    @app.template_filter("d")
    def format_date(value, short=False):
        if not value:
            return "—"
        if isinstance(value, str):
            value = datetime.fromisoformat(value[:10]).date()
        if short:
            return f"{value.day} {MONTHS[value.month - 1]}"
        return value.strftime("%d.%m.%Y")

    @app.template_filter("dt")
    def format_datetime(value):
        if not value:
            return "—"
        value = datetime.fromisoformat(value) if isinstance(value, str) else value
        return value.strftime("%d.%m.%Y %H:%M")

    @app.template_filter("money")
    def format_money(value, currency="USD"):
        if value is None:
            return "—"
        sign = refs.CURRENCIES.get(currency, currency)
        text = f"{value:,.0f}".replace(",", " ") if abs(value - round(value)) < 0.005 \
            else f"{value:,.2f}".replace(",", " ").replace(".", ",")
        return f"{text} {sign}"

    @app.template_filter("plain")
    def format_plain(value):
        """Число для поля форми: 12000 замість 12000.0."""
        if value is None:
            return ""
        return f"{value:.0f}" if abs(value - round(value)) < 0.005 else f"{value:.2f}"

    @app.template_filter("num")
    def format_num(value, digits=2):
        if value is None:
            return "—"
        return f"{value:.{digits}f}".replace(".", ",")

    @app.template_filter("pct")
    def format_pct(value):
        if value is None:
            return "—"
        return f"{value * 100:.0f} %"

    def asset(filename):
        """Посилання на власний файл з позначкою версії, щоб браузер не показував стару копію."""
        try:
            version = int(os.path.getmtime(os.path.join(app.static_folder, filename)))
        except OSError:
            version = 0
        return url_for("static", filename=filename, v=version)

    @app.context_processor
    def inject():
        return {
            "can": auth.can,
            "csrf_token": auth.csrf_token,
            "refs": refs,
            "calc": calc,
            "today": date.today(),
            "current_user": g.get("user"),
            "event_status": stats.event_status,
            "formulas": formulas.FORMULAS,
            "date_of": lambda s: date.fromisoformat(str(s)[:10]),
            "asset": asset,
        }
