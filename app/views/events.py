"""Блок Б1: планування кампанії — подія, кошторис, оцінка доцільності (ФВ-01…ФВ-04)."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

from .. import refs, stats
from ..auth import require
from ..db import execute, get_db, query
from . import clean, get_event, parse_amount, parse_date, parse_int

bp = Blueprint("events", __name__)


@bp.route("/")
def index():
    """Перелік подій з фільтрами за статусом, рекомендацією та окупністю."""
    all_cards = stats.event_cards()
    filters = {
        "status": request.args.get("status") if request.args.get("status") in refs.EVENT_STATUSES else None,
        "rec": request.args.get("rec") if request.args.get("rec") in refs.RECOMMENDATIONS else None,
        "roi": request.args.get("roi") if request.args.get("roi") in refs.ROI_STATUSES else None,
    }
    cards = all_cards
    if filters["status"]:
        cards = [c for c in cards if c["status"] == filters["status"]]
    if filters["rec"]:
        cards = [c for c in cards if c["status"] == "planned" and c["recommendation"] == filters["rec"]]
    if filters["roi"]:
        cards = [c for c in cards if c["roi_status"] == filters["roi"]]
    counts = {
        "status": {k: sum(1 for c in all_cards if c["status"] == k) for k in refs.EVENT_STATUSES},
        "rec": {k: sum(1 for c in all_cards if c["status"] == "planned" and c["recommendation"] == k)
                for k in refs.RECOMMENDATIONS},
        "roi": {k: sum(1 for c in all_cards if c["roi_status"] == k) for k in refs.ROI_STATUSES},
    }
    categories = query("SELECT * FROM cost_categories WHERE is_active = 1 ORDER BY id")
    return render_template("events/index.html", cards=cards, total=len(all_cards), filters=filters,
                           counts=counts, categories=categories)


@bp.route("/formulas")
def formulas():
    """Пояснення всіх формул і показників простими словами."""
    return render_template("events/formulas.html")


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
        "address": clean(f.get("address"), 300),
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


def _save_initial_costs(event_id):
    """Планові витрати з вікна «Нова подія»: рядки категорія + опис + сума."""
    cats = request.form.getlist("cost_category")
    descs = request.form.getlist("cost_description")
    sums = request.form.getlist("cost_planned")
    valid = {r["id"] for r in query("SELECT id FROM cost_categories")}
    added = 0
    for cat, desc, amount in zip(cats, descs, sums):
        cat_id = parse_int(cat, 1, 10**9)
        planned = parse_amount(amount) if (amount or "").strip() else None
        if cat_id in valid and planned:
            execute("INSERT INTO cost_items (event_id, category_id, description, planned) VALUES (?, ?, ?, ?)",
                    (event_id, cat_id, clean(desc, 300), planned))
            added += 1
    return added


@bp.route("/events/new", methods=["GET", "POST"])
@require("event_edit")
def new():
    if request.method == "POST":
        data, errors = _read_event_form()
        if not errors:
            eid = execute(
                "INSERT INTO events (name, city, address, start_date, end_date, goal, has_booth, currency, "
                "close_rate, avg_deal) VALUES (:name, :city, :address, :start_date, :end_date, :goal, :has_booth, "
                ":currency, :close_rate, :avg_deal)", data)
            added = _save_initial_costs(eid)
            flash("Подію створено." + (f" Додано витрат: {added}." if added else " Додайте витрати.")
                  + " Далі оцініть доцільність участі.", "success")
            return redirect(url_for("events.detail", event_id=eid))
        for e in errors:
            flash(e, "danger")
        return render_template("events/form.html", event=data, is_new=True)
    blank = {"name": None, "city": None, "address": None, "start_date": None, "end_date": None, "goal": None,
             "has_booth": 1, "currency": "USD", "close_rate": None, "avg_deal": None}
    return render_template("events/form.html", event=blank, is_new=True)


@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@require("event_edit")
def edit(event_id):
    event = get_event(event_id)
    if request.method == "POST":
        data, errors = _read_event_form()
        if not errors:
            data["id"] = event_id
            execute(
                "UPDATE events SET name = :name, city = :city, address = :address, start_date = :start_date, end_date = :end_date, "
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
    return render_template(
        "events/detail.html", event=event, phase=stats.event_phase(event),
        roi=stats.roi_summary(event_id), score=stats.score_summary(event_id),
        dash=stats.dashboard(event), by_category=stats.costs_by_category(event_id), tab="overview")


@bp.route("/events/<int:event_id>/costs")
def costs(event_id):
    """Вікно витрат: план і факт за позиціями та категоріями (ФВ-02, ФВ-03)."""
    event = get_event(event_id)
    items = query(
        "SELECT ci.*, cc.name AS category FROM cost_items ci JOIN cost_categories cc ON cc.id = ci.category_id "
        "WHERE ci.event_id = ? ORDER BY cc.id, ci.id", (event_id,))
    categories = query("SELECT * FROM cost_categories WHERE is_active = 1 ORDER BY id")
    return render_template(
        "events/costs.html", event=event, phase=stats.event_phase(event), items=items, categories=categories,
        by_category=stats.costs_by_category(event_id), totals=stats.cost_totals(event_id),
        roi=stats.roi_summary(event_id), tab="costs")


def _read_cost_form():
    planned = parse_amount(request.form.get("planned") or 0)
    actual_raw = (request.form.get("actual") or "").strip()
    actual = parse_amount(actual_raw) if actual_raw else None
    ok = planned is not None and (not actual_raw or actual is not None)
    return planned, actual, ok


@bp.route("/events/<int:event_id>/costs", methods=["POST"])
@require("event_edit")
def add_cost(event_id):
    get_event(event_id)
    planned, actual, ok = _read_cost_form()
    category = parse_int(request.form.get("category_id"), 1, 10**9)
    if not ok or not category or (not planned and actual is None) or not query(
            "SELECT 1 FROM cost_categories WHERE id = ?", (category,), one=True):
        flash("Оберіть категорію і вкажіть планову або фактичну суму (число, не менше нуля).", "danger")
    else:
        execute("INSERT INTO cost_items (event_id, category_id, description, planned, actual) VALUES (?, ?, ?, ?, ?)",
                (event_id, category, clean(request.form.get("description"), 300), planned, actual))
        flash("Позицію кошторису додано.", "success")
    return redirect(url_for("events.costs", event_id=event_id))


@bp.route("/events/<int:event_id>/costs/<int:item_id>", methods=["POST"])
@require("event_edit")
def update_cost(event_id, item_id):
    if request.form.get("action") == "delete":
        execute("DELETE FROM cost_items WHERE id = ? AND event_id = ?", (item_id, event_id))
        flash("Позицію вилучено.", "success")
        return redirect(url_for("events.costs", event_id=event_id))
    planned, actual, ok = _read_cost_form()
    if not ok:
        flash("Суми мають бути числами, не меншими за нуль.", "danger")
    else:
        execute("UPDATE cost_items SET planned = ?, actual = ?, description = COALESCE(?, description) "
                "WHERE id = ? AND event_id = ?",
                (planned, actual, clean(request.form.get("description"), 300), item_id, event_id))
        flash("Суми оновлено.", "success")
    return redirect(url_for("events.costs", event_id=event_id))


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
