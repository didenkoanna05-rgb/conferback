"""Блоки Б3, Б4 і БС: фіксація лідів, синхронізація, черга дій, фолоу-апи та угоди (ФВ-08…ФВ-16)."""
import sqlite3
import uuid
from datetime import date, datetime, timedelta

from flask import (Blueprint, abort, flash, g, jsonify, redirect, render_template,
                   request, url_for)

from .. import calc, refs, stats
from ..auth import can, require
from ..db import execute, get_db, query
from . import clean, get_event, parse_amount, parse_date, parse_int, users_with_role

bp = Blueprint("leads", __name__)


def save_lead(event_id, data, user_id):
    """Збереження зафіксованої розмови (алгоритм рис. 3.10).

    Обов'язкові лише ім'я та зацікавленість: решту можна дописати після події.
    Якщо обрано контакт із цільового списку, ім'я та компанія беруться з нього (ФВ-09).
    Дата фолоу-апу визначається за формулою (3.4), якщо її не вказано вручну (ФВ-12).
    """
    target_id = parse_int(data.get("target_id"), 1, 10**12)
    target = None
    if target_id:
        target = query("SELECT * FROM targets WHERE id = ? AND event_id = ?", (target_id, event_id), one=True)
        if target is None:
            target_id = None

    full_name = clean(data.get("full_name"), 200) or (target["full_name"] if target else None)
    intent = parse_int(data.get("intent"), 1, 3)
    if not full_name:
        raise ValueError("Вкажіть ім'я співрозмовника.")
    if intent is None:
        raise ValueError("Оберіть рівень зацікавленості.")

    captured_at = data.get("captured_at")
    try:
        captured = datetime.fromisoformat(str(captured_at)[:19]) if captured_at else datetime.now()
    except ValueError:
        captured = datetime.now()

    no_prospect = str(data.get("no_prospect", "")) in ("1", "true", "on")
    if no_prospect:
        status, due = "no_action", None
    else:
        manual = parse_date(data.get("due_date")) if data.get("due_date") else None
        status, due = "new", (manual or calc.followup_date(intent, captured.date())).isoformat()

    owner_id = parse_int(data.get("owner_id"), 1, 10**12)
    if owner_id is None and g.get("user") and "manager" in g.user["roles"]:
        owner_id = user_id

    row = {
        "event_id": event_id,
        "target_id": target_id,
        "full_name": full_name,
        "company": clean(data.get("company"), 200) or (target["company"] if target else None),
        "position": clean(data.get("position"), 200) or (target["position"] if target else None),
        "email": clean(data.get("email"), 200) or (target["email"] if target else None),
        "phone": clean(data.get("phone"), 50) or (target["phone"] if target else None),
        "icp_fit": parse_int(data.get("icp_fit"), 1, 3),
        "intent": intent,
        "need_topic": clean(data.get("need_topic"), 200),
        "details": clean(data.get("details"), 3000),
        "next_step": clean(data.get("next_step"), 200),
        "owner_id": owner_id,
        "due_date": due,
        "captured_at": captured.isoformat(timespec="seconds"),
        "captured_by": user_id,
        "status": status,
        "client_uid": clean(data.get("client_uid"), 64) or uuid.uuid4().hex,
    }
    return execute(
        "INSERT INTO leads (event_id, target_id, full_name, company, position, email, phone, icp_fit, intent, "
        "need_topic, details, next_step, owner_id, due_date, captured_at, captured_by, status, client_uid) "
        "VALUES (:event_id, :target_id, :full_name, :company, :position, :email, :phone, :icp_fit, :intent, "
        ":need_topic, :details, :next_step, :owner_id, :due_date, :captured_at, :captured_by, :status, :client_uid)",
        row)


@bp.route("/events/<int:event_id>/capture", methods=["GET", "POST"])
@require("lead_capture")
def capture(event_id):
    """Форма фіксації розмови. З JavaScript запис іде через /api/sync, без нього — звичайною формою."""
    event = get_event(event_id)
    if request.method == "POST":
        try:
            save_lead(event_id, request.form, g.user["id"])
            flash("Розмову збережено.", "success")
        except (ValueError, sqlite3.IntegrityError) as e:
            flash(str(e), "danger")
        return redirect(url_for("leads.capture", event_id=event_id))
    targets = query(
        "SELECT id, full_name, company, position, status FROM targets WHERE event_id = ? "
        "AND status NOT IN ('declined') ORDER BY CASE status WHEN 'meeting' THEN 0 WHEN 'confirmed' THEN 1 "
        "ELSE 2 END, full_name", (event_id,))
    recent = query(
        "SELECT id, full_name, company, intent, captured_at FROM leads WHERE event_id = ? AND captured_by = ? "
        "ORDER BY captured_at DESC LIMIT 5", (event_id, g.user["id"]))
    return render_template(
        "leads/capture.html", event=event, targets=targets, managers=users_with_role("manager"),
        recent=recent, delays=calc.FOLLOWUP_DELAY_DAYS)


@bp.route("/api/sync", methods=["POST"])
@require("lead_capture")
def api_sync():
    """Приймання записів, накопичених пристроєм (ФВ-13, ДВ-05, ДВ-06).

    Повторне надсилання не створює дублікатів завдяки client_uid,
    а помилковий запис відхиляється поодинці і не зупиняє решту.
    """
    payload = request.get_json(silent=True) or {}
    saved = skipped = rejected = 0
    done, errors = [], {}
    for item in payload.get("leads", [])[:500]:
        if not isinstance(item, dict):
            rejected += 1
            continue
        uid = str(item.get("client_uid") or "")[:64]
        if uid and query("SELECT id FROM leads WHERE client_uid = ?", (uid,), one=True):
            skipped += 1
            done.append(uid)
            continue
        event_id = parse_int(item.get("event_id"), 1, 10**12)
        if not event_id or not query("SELECT 1 FROM events WHERE id = ?", (event_id,), one=True):
            rejected += 1
            errors[uid] = "Подію не знайдено."
            continue
        try:
            save_lead(event_id, item, g.user["id"])
            saved += 1
            done.append(uid)
        except (ValueError, sqlite3.Error) as e:
            get_db().rollback()
            rejected += 1
            errors[uid] = str(e)
    return jsonify({"saved": saved, "skipped": skipped, "rejected": rejected, "done": done, "errors": errors})


@bp.route("/events/<int:event_id>/leads")
def event_leads(event_id):
    event = get_event(event_id)
    intent = parse_int(request.args.get("intent"), 1, 3)
    status = request.args.get("status")
    q = (request.args.get("q") or "").strip()
    sql = ("SELECT l.*, u.full_name AS owner_name, d.stage AS deal_stage, d.amount AS deal_amount "
           "FROM leads l LEFT JOIN users u ON u.id = l.owner_id LEFT JOIN deals d ON d.lead_id = l.id "
           "WHERE l.event_id = ?")
    args = [event_id]
    if intent:
        sql += " AND l.intent = ?"
        args.append(intent)
    if status in refs.LEAD_STATUSES:
        sql += " AND l.status = ?"
        args.append(status)
    if q:
        sql += " AND (l.full_name LIKE ? OR l.company LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY l.captured_at DESC"
    return render_template("leads/list.html", event=event, phase=stats.event_phase(event),
                           leads=query(sql, args), intent=intent, status=status, q=q, tab="leads")


def _get_lead(lead_id):
    lead = query(
        "SELECT l.*, u.full_name AS owner_name, c.full_name AS captured_name, e.name AS event_name, "
        "e.currency, t.status AS target_status FROM leads l JOIN events e ON e.id = l.event_id "
        "LEFT JOIN users u ON u.id = l.owner_id LEFT JOIN users c ON c.id = l.captured_by "
        "LEFT JOIN targets t ON t.id = l.target_id WHERE l.id = ?", (lead_id,), one=True)
    if lead is None:
        abort(404)
    return lead


@bp.route("/leads/<int:lead_id>")
def detail(lead_id):
    lead = _get_lead(lead_id)
    followups = query(
        "SELECT f.*, u.full_name AS user_name FROM followups f LEFT JOIN users u ON u.id = f.user_id "
        "WHERE f.lead_id = ? ORDER BY f.done_on DESC, f.id DESC", (lead_id,))
    deal = query("SELECT * FROM deals WHERE lead_id = ?", (lead_id,), one=True)
    return render_template("leads/detail.html", lead=lead, followups=followups, deal=deal,
                           managers=users_with_role("manager"))


@bp.route("/leads/<int:lead_id>/edit", methods=["POST"])
@require("lead_edit")
def edit(lead_id):
    lead = _get_lead(lead_id)
    f = request.form
    name = clean(f.get("full_name"), 200)
    intent = parse_int(f.get("intent"), 1, 3)
    if not name or intent is None:
        flash("Ім'я та зацікавленість обов'язкові.", "danger")
        return redirect(url_for("leads.detail", lead_id=lead_id))
    owner = parse_int(f.get("owner_id"), 1, 10**12)
    due = parse_date(f.get("due_date")) if f.get("due_date") else None
    status = lead["status"]
    if f.get("no_prospect") == "1":
        status, due = "no_action", None
    elif status == "no_action":
        status = "new"
        due = due or calc.followup_date(intent)
    execute(
        "UPDATE leads SET full_name = ?, company = ?, position = ?, email = ?, phone = ?, icp_fit = ?, intent = ?, "
        "need_topic = ?, details = ?, next_step = ?, owner_id = ?, due_date = ?, status = ? WHERE id = ?",
        (name, clean(f.get("company"), 200), clean(f.get("position"), 200), clean(f.get("email"), 200),
         clean(f.get("phone"), 50), parse_int(f.get("icp_fit"), 1, 3), intent, clean(f.get("need_topic"), 200),
         clean(f.get("details"), 3000), clean(f.get("next_step"), 200), owner,
         due.isoformat() if due else None, status, lead_id))
    flash("Картку ліда оновлено.", "success")
    return redirect(url_for("leads.detail", lead_id=lead_id))


@bp.route("/leads/<int:lead_id>/followups", methods=["POST"])
@require("followup")
def add_followup(lead_id):
    """Реєстрація фолоу-апу і переведення ліда в наступний стан (рис. 3.9, ФВ-15)."""
    lead = _get_lead(lead_id)
    f = request.form
    channel, result = f.get("channel"), f.get("result")
    if channel not in refs.FOLLOWUP_CHANNELS or result not in refs.FOLLOWUP_RESULTS:
        flash("Оберіть канал і результат.", "danger")
        return redirect(url_for("leads.detail", lead_id=lead_id))
    done_on = parse_date(f.get("done_on")) or date.today()
    db = get_db()
    db.execute("INSERT INTO followups (lead_id, channel, done_on, result, note, user_id) VALUES (?, ?, ?, ?, ?, ?)",
               (lead_id, channel, done_on.isoformat(), result, clean(f.get("note"), 2000), g.user["id"]))
    if result == "refused":
        status, due = ("closed", None) if lead["status"] != "won" else ("won", None)
    else:
        nxt = parse_date(f.get("next_date"))
        if nxt is None or nxt < done_on:
            nxt = done_on + timedelta(days=refs.FOLLOWUP_RETRY_DAYS[result])
        status, due = ("in_progress", nxt.isoformat()) if lead["status"] != "won" else ("won", None)
    db.execute("UPDATE leads SET status = ?, due_date = ? WHERE id = ?", (status, due, lead_id))
    db.commit()
    if result == "agreement" and not query("SELECT 1 FROM deals WHERE lead_id = ?", (lead_id,), one=True):
        flash("Фолоу-ап збережено. Зареєструйте угоду для цього ліда.", "success")
        return redirect(url_for("leads.detail", lead_id=lead_id) + "#deal")
    flash(f"Фолоу-ап з {lead['full_name']} збережено.", "success")
    back = f.get("back") or ""
    return redirect(back if back.startswith("/") and not back.startswith("//")
                    else url_for("leads.detail", lead_id=lead_id))


@bp.route("/leads/<int:lead_id>/deal", methods=["POST"])
@require("deal")
def save_deal(lead_id):
    """Реєстрація або зміна угоди, ФВ-16."""
    lead = _get_lead(lead_id)
    f = request.form
    amount = parse_amount(f.get("amount"))
    stage, rtype = f.get("stage"), f.get("revenue_type")
    if amount is None or stage not in refs.DEAL_STAGES or rtype not in refs.REVENUE_TYPES:
        flash("Вкажіть суму, стадію і тип доходу.", "danger")
        return redirect(url_for("leads.detail", lead_id=lead_id) + "#deal")
    close = parse_date(f.get("close_date")) if f.get("close_date") else None
    if stage == "won" and close is None:
        close = date.today()
    db = get_db()
    db.execute(
        "INSERT INTO deals (lead_id, amount, stage, revenue_type, close_date) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (lead_id) DO UPDATE SET amount = excluded.amount, stage = excluded.stage, "
        "revenue_type = excluded.revenue_type, close_date = excluded.close_date",
        (lead_id, amount, stage, rtype, close.isoformat() if close else None))
    if stage == "won":
        db.execute("UPDATE leads SET status = 'won', due_date = NULL WHERE id = ?", (lead_id,))
    elif stage == "lost":
        db.execute("UPDATE leads SET status = 'closed', due_date = NULL WHERE id = ?", (lead_id,))
    elif lead["status"] in ("won", "closed", "new", "no_action"):
        db.execute("UPDATE leads SET status = 'in_progress', due_date = COALESCE(due_date, ?) WHERE id = ?",
                   ((date.today() + timedelta(days=7)).isoformat(), lead_id))
    db.commit()
    flash("Угоду збережено.", "success")
    return redirect(url_for("leads.detail", lead_id=lead_id))


@bp.route("/queue")
@require("queue")
def queue():
    """Черга дій з розподілом на прострочені, сьогоднішні та майбутні, ФВ-14."""
    mine = request.args.get("mine", "1" if g.user["roles"] == {"manager"} else "0") == "1"
    event_id = parse_int(request.args.get("event"), 1, 10**12)
    sql = ("SELECT l.*, e.name AS event_name, u.full_name AS owner_name FROM leads l "
           "JOIN events e ON e.id = l.event_id LEFT JOIN users u ON u.id = l.owner_id "
           "WHERE l.status IN ('new', 'in_progress') AND l.due_date IS NOT NULL")
    args = []
    if mine:
        sql += " AND l.owner_id = ?"
        args.append(g.user["id"])
    if event_id:
        sql += " AND l.event_id = ?"
        args.append(event_id)
    sql += " ORDER BY l.due_date ASC, l.intent DESC, l.captured_at ASC"
    groups = calc.split_queue(query(sql, args))
    events = query("SELECT DISTINCT e.id, e.name FROM events e JOIN leads l ON l.event_id = e.id "
                   "WHERE l.status IN ('new', 'in_progress') ORDER BY e.start_date DESC")
    return render_template("leads/queue.html", groups=groups, mine=mine, event_id=event_id, events=events,
                           can_followup=can("followup"))
