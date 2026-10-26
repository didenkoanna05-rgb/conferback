"""Блок Б1: планування кампанії — подія, кошторис, оцінка доцільності (ФВ-01…ФВ-04)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import refs, stats
from ..auth import require
from ..db import execute, get_db, query
from . import clean, get_event, parse_amount, parse_date, parse_int

bp = Blueprint("events", __name__)


@bp.route("/")
def index():
    cards = stats.event_cards()
    return render_template("events/index.html", cards=cards)


@bp.route("/capture")
@require("lead_capture")
def capture_choose():
    """Перехід до форми фіксації: якщо подія триває одна, відкриваємо її одразу (ДВ-08)."""
    cards = [c for c in stats.event_cards() if c["phase"] != "finished"]
    ongoing = [c for c in cards if c["phase"] == "ongoing"]
    if len(ongoing) == 1:
        return redirect(url_for("leads.capture", event_id=ongoing[0]["event"]["id"]))
    return render_template("events/choose.html", cards=cards)


def _read_event_form():
    f = request.form
    data = {
        "name": clean(f.get("name"), 200),
        "city": clean(f.get("city"), 100),
        "start_date": parse_date(f.get("start_date")),
        "end_date": parse_date(f.get("end_date")),
        "goal": clean(f.get("goal"), 2000),
        "has_booth": 1 if f.get("has_booth") == "1" else 0,
        "currency": f.get("currency") if f.get("currency") in refs.CURRENCIES else "USD",
        "close_rate": None,
        "avg_deal": parse_amount(f.get("avg_deal")) if f.get("avg_deal") else None,
    }
    rate = parse_amount(f.get("close_rate")) if f.get("close_rate") else None
    if rate is not None and rate <= 100:
        data["close_rate"] = rate / 100
    errors = []
    if not data["name"]:
        errors.append("Вкажіть назву події.")
    if not data["start_date"] or not data["end_date"]:
        errors.append("Вкажіть дати початку і кінця.")
    elif data["end_date"] < data["start_date"]:
        errors.append("Дата кінця не може бути раніше дати початку.")
    return data, errors


@bp.route("/events/new", methods=["GET", "POST"])
@require("event_edit")
def new():
    if request.method == "POST":
        data, errors = _read_event_form()
        if not errors:
            eid = execute(
                "INSERT INTO events (name, city, start_date, end_date, goal, has_booth, currency, close_rate, avg_deal) "
                "VALUES (:name, :city, :start_date, :end_date, :goal, :has_booth, :currency, :close_rate, :avg_deal)",
                data)
            flash("Кампанію створено. Додайте кошторис і оцініть доцільність участі.", "success")
            return redirect(url_for("events.detail", event_id=eid))
        for e in errors:
            flash(e, "danger")
        return render_template("events/form.html", event=data, is_new=True)
    return render_template("events/form.html", event={"has_booth": 1, "currency": "USD"}, is_new=True)


@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@require("event_edit")
def edit(event_id):
    event = get_event(event_id)
    if request.method == "POST":
        data, errors = _read_event_form()
        if not errors:
            data["id"] = event_id
            execute(
                "UPDATE events SET name = :name, city = :city, start_date = :start_date, end_date = :end_date, "
                "goal = :goal, has_booth = :has_booth, currency = :currency, close_rate = :close_rate, "
                "avg_deal = :avg_deal WHERE id = :id", data)
            flash("Зміни збережено.", "success")
            return redirect(url_for("events.detail", event_id=event_id))
        for e in errors:
            flash(e, "danger")
        data["id"] = event_id
        return render_template("events/form.html", event=data, is_new=False)
    return render_template("events/form.html", event=event, is_new=False)


@bp.route("/events/<int:event_id>/delete", methods=["POST"])
@require("event_delete")
def delete(event_id):
    event = get_event(event_id)
    execute("DELETE FROM events WHERE id = ?", (event_id,))
    flash(f"Подію «{event['name']}» вилучено разом з усіма даними.", "success")
    return redirect(url_for("events.index"))


@bp.route("/events/<int:event_id>")
def detail(event_id):
    event = get_event(event_id)
    costs = query(
        "SELECT ci.*, cc.name AS category FROM cost_items ci JOIN cost_categories cc ON cc.id = ci.category_id "
        "WHERE ci.event_id = ? ORDER BY ci.amount DESC", (event_id,))
    categories = query("SELECT * FROM cost_categories WHERE is_active = 1 ORDER BY id")
    return render_template(
        "events/detail.html", event=event, phase=stats.event_phase(event), costs=costs,
        categories=categories, roi=stats.roi_summary(event_id), score=stats.score_summary(event_id),
        dash=stats.dashboard(event), tab="overview")


@bp.route("/events/<int:event_id>/costs", methods=["POST"])
@require("event_edit")
def add_cost(event_id):
    get_event(event_id)
    amount = parse_amount(request.form.get("amount"))
    category = parse_int(request.form.get("category_id"), 1, 10**9)
    if amount is None or not category or not query(
            "SELECT 1 FROM cost_categories WHERE id = ?", (category,), one=True):
        flash("Оберіть категорію і вкажіть суму (число, не менше нуля).", "danger")
    else:
        execute("INSERT INTO cost_items (event_id, category_id, description, amount) VALUES (?, ?, ?, ?)",
                (event_id, category, clean(request.form.get("description"), 300), amount))
        flash("Позицію кошторису додано.", "success")
    return redirect(url_for("events.detail", event_id=event_id) + "#costs")


@bp.route("/events/<int:event_id>/costs/<int:item_id>/delete", methods=["POST"])
@require("event_edit")
def delete_cost(event_id, item_id):
    execute("DELETE FROM cost_items WHERE id = ? AND event_id = ?", (item_id, event_id))
    flash("Позицію вилучено.", "success")
    return redirect(url_for("events.detail", event_id=event_id) + "#costs")


@bp.route("/events/<int:event_id>/score", methods=["POST"])
@require("event_score")
def save_score(event_id):
    get_event(event_id)
    db = get_db()
    for c in query("SELECT id FROM criteria WHERE is_active = 1"):
        value = parse_int(request.form.get(f"c{c['id']}"), 0, 5)
        if value is None:
            db.execute("DELETE FROM event_scores WHERE event_id = ? AND criterion_id = ?", (event_id, c["id"]))
        else:
            db.execute(
                "INSERT INTO event_scores (event_id, criterion_id, score) VALUES (?, ?, ?) "
                "ON CONFLICT (event_id, criterion_id) DO UPDATE SET score = excluded.score",
                (event_id, c["id"], value))
    db.commit()
    flash("Оцінку збережено.", "success")
    return redirect(url_for("events.detail", event_id=event_id) + "#score")
