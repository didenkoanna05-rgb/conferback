"""Блоки Б3, Б4 і БС: фіксація лідів, синхронізація, черга дій, фолоу-апи та угоди (ФВ-08…ФВ-16)."""
import sqlite3
import uuid
from datetime import date, datetime, timedelta

from flask import (Blueprint, Response, abort, flash, g, jsonify, redirect, render_template,
                   request, url_for)

from .. import calc, importer, refs, stats
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
        "linkedin_url": clean(data.get("linkedin_url"), 300) or (target["linkedin_url"] if target else None),
        "channel": data.get("channel") if data.get("channel") in refs.CHANNELS
        else (target["channel"] if target else None),
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
    lead_id = execute(
        "INSERT INTO leads (event_id, target_id, full_name, company, position, email, phone, linkedin_url, channel, "
        "icp_fit, intent, need_topic, details, next_step, owner_id, due_date, captured_at, captured_by, status, "
        "client_uid) VALUES (:event_id, :target_id, :full_name, :company, :position, :email, :phone, :linkedin_url, "
        ":channel, :icp_fit, :intent, :need_topic, :details, :next_step, :owner_id, :due_date, :captured_at, "
        ":captured_by, :status, :client_uid)", row)
    if target_id:
        # Розмова з контактом зі списку відбулася
        execute("UPDATE targets SET status = 'met' WHERE id = ?", (target_id,))
    return lead_id


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
        "SELECT id, full_name, company, position, status, meeting_at FROM targets WHERE event_id = ? "
        "AND status NOT IN ('not_interested', 'met') ORDER BY status != 'meeting', meeting_at, priority, full_name",
        (event_id,))
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
    """Ліди події як у CRM: усі, з ким говорили, і ті, з ким не зустрілися, але написати ще можна."""
    event = get_event(event_id)
    view = request.args.get("view", "all")
    channel = request.args.get("channel")
    status = request.args.get("status")
    q = (request.args.get("q") or "").strip()
    sql = ("SELECT l.*, u.full_name AS owner_name, d.stage AS deal_stage, d.amount AS deal_amount, "
           "(SELECT MAX(done_on) FROM followups f WHERE f.lead_id = l.id) AS last_contact "
           "FROM leads l LEFT JOIN users u ON u.id = l.owner_id LEFT JOIN deals d ON d.lead_id = l.id "
           "WHERE l.event_id = ?")
    args = [event_id]
    if view == "met":
        sql += " AND l.met = 1"
    elif view == "unmet":
        sql += " AND l.met = 0"
    if channel in refs.CHANNELS:
        sql += " AND l.channel = ?"
        args.append(channel)
    if status in refs.LEAD_STATUSES:
        sql += " AND l.status = ?"
        args.append(status)
    if q:
        sql += " AND (l.full_name LIKE ? OR l.company LIKE ?)"
        args += [f"%{q}%", f"%{q}%"]
    sql += " ORDER BY l.status IN ('won', 'closed', 'no_action'), l.due_date IS NULL, l.due_date, l.intent DESC"
    leads = query(sql, args) if view != "missed" else []

    # Контакти зі списку, з якими не зустрілися і яких ще не взяли в роботу
    missed_sql = ("SELECT t.*, u.full_name AS owner_name FROM targets t LEFT JOIN users u ON u.id = t.owner_id "
                  "WHERE t.event_id = ? AND t.status IN ({}) "
                  "AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.target_id = t.id)").format(
        ",".join("?" * len(refs.TARGET_REACHABLE)))
    missed_args = [event_id, *refs.TARGET_REACHABLE]
    if channel in refs.CHANNELS:
        missed_sql += " AND t.channel = ?"
        missed_args.append(channel)
    if q:
        missed_sql += " AND (t.full_name LIKE ? OR t.company LIKE ?)"
        missed_args += [f"%{q}%", f"%{q}%"]
    missed = query(missed_sql + " ORDER BY t.priority, t.full_name", missed_args) \
        if view in ("all", "missed") and not status else []
    counts = query(
        "SELECT SUM(met = 1) AS met, SUM(met = 0) AS unmet, COUNT(*) AS total FROM leads WHERE event_id = ?",
        (event_id,), one=True)
    return render_template("leads/list.html", event=event, phase=stats.event_phase(event), leads=leads,
                           missed=missed, view=view, channel=channel, status=status, q=q, counts=counts,
                           managers=users_with_role("manager"), tab="leads")


def take_target(target, user_id):
    """Взяти в роботу контакт, з яким не зустрілися: створюється лід без розмови (met = 0)."""
    return execute(
        "INSERT INTO leads (event_id, target_id, full_name, company, position, email, phone, linkedin_url, channel, "
        "met, owner_id, due_date, captured_at, captured_by, status, details, next_step, client_uid) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?, 'new', ?, ?, ?)",
        (target["event_id"], target["id"], target["full_name"], target["company"], target["position"],
         target["email"], target["phone"], target["linkedin_url"], target["channel"],
         target["owner_id"] or (user_id if "manager" in g.user["roles"] else None),
         date.today().isoformat(), datetime.now().isoformat(timespec="seconds"), user_id,
         target["note"], "Лист «шкода, що не зустрілися»", uuid.uuid4().hex))


@bp.route("/targets/<int:target_id>/take", methods=["POST"])
@require("followup")
def take(target_id):
    target = query("SELECT * FROM targets WHERE id = ?", (target_id,), one=True)
    if target is None:
        abort(404)
    if query("SELECT 1 FROM leads WHERE target_id = ?", (target_id,), one=True):
        flash("Цей контакт уже в роботі.", "info")
    else:
        take_target(target, g.user["id"])
        flash(f"{target['full_name']} — у роботі, фолоу-ап на сьогодні.", "success")
    return redirect(url_for("leads.event_leads", event_id=target["event_id"], view=request.args.get("view", "all")))


@bp.route("/events/<int:event_id>/take-all", methods=["POST"])
@require("followup")
def take_all(event_id):
    get_event(event_id)
    rows = query(
        "SELECT * FROM targets t WHERE t.event_id = ? AND t.status IN ({}) "
        "AND NOT EXISTS (SELECT 1 FROM leads l WHERE l.target_id = t.id)".format(
            ",".join("?" * len(refs.TARGET_REACHABLE))), (event_id, *refs.TARGET_REACHABLE))
    for t in rows:
        take_target(t, g.user["id"])
    flash(f"Узято в роботу контактів: {len(rows)}.", "success")
    return redirect(url_for("leads.event_leads", event_id=event_id, view="unmet"))


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
    if not name or (intent is None and lead["met"]):
        flash("Ім'я та зацікавленість обов'язкові.", "danger")
        return redirect(url_for("leads.detail", lead_id=lead_id))
    owner = parse_int(f.get("owner_id"), 1, 10**12)
    due = parse_date(f.get("due_date")) if f.get("due_date") else None
    status = lead["status"]
    if f.get("no_prospect") == "1":
        status, due = "no_action", None
    elif status == "no_action":
        status = "new"
        due = due or (calc.followup_date(intent) if intent else date.today())
    channel = f.get("channel") if f.get("channel") in refs.CHANNELS else None
    execute(
        "UPDATE leads SET full_name = ?, company = ?, position = ?, email = ?, phone = ?, linkedin_url = ?, "
        "channel = ?, icp_fit = ?, intent = ?, "
        "need_topic = ?, details = ?, next_step = ?, owner_id = ?, due_date = ?, status = ? WHERE id = ?",
        (name, clean(f.get("company"), 200), clean(f.get("position"), 200), clean(f.get("email"), 200),
         clean(f.get("phone"), 50), clean(f.get("linkedin_url"), 300), channel,
         parse_int(f.get("icp_fit"), 1, 3), intent, clean(f.get("need_topic"), 200),
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
    if channel not in refs.CHANNELS or result not in refs.FOLLOWUP_RESULTS:
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


def sync_lead_with_deal(db, lead, stage):
    """Стан ліда йде за етапом угоди: укладена — «Угода», втрачена — «Закрито без угоди»."""
    if stage == "won":
        db.execute("UPDATE leads SET status = 'won', due_date = NULL WHERE id = ?", (lead["id"],))
    elif stage == "lost":
        db.execute("UPDATE leads SET status = 'closed', due_date = NULL WHERE id = ?", (lead["id"],))
    elif lead["status"] != "in_progress" or not lead["due_date"]:
        # Угода ще в роботі: лід лишається в черзі дій
        db.execute("UPDATE leads SET status = 'in_progress', due_date = COALESCE(due_date, ?) WHERE id = ?",
                   ((date.today() + timedelta(days=7)).isoformat(), lead["id"]))


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
    sync_lead_with_deal(db, lead, stage)
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


@bp.route("/deals")
@require("deals_view")
def deals():
    """Дошка угод за етапами з усіх подій."""
    event_id = parse_int(request.args.get("event"), 1, 10**12)
    sql = ("SELECT d.*, l.full_name, l.company, l.channel, l.id AS lead_id, l.owner_id, e.name AS event_name, "
           "e.currency, u.full_name AS owner_name FROM deals d JOIN leads l ON l.id = d.lead_id "
           "JOIN events e ON e.id = l.event_id LEFT JOIN users u ON u.id = l.owner_id")
    args = []
    if event_id:
        sql += " WHERE l.event_id = ?"
        args.append(event_id)
    rows = query(sql + " ORDER BY COALESCE(d.close_date, '9999') DESC, d.amount DESC", args)
    columns = {k: [r for r in rows if r["stage"] == k] for k in refs.DEAL_STAGES}
    totals = {k: sum(r["amount"] for r in v) for k, v in columns.items()}
    events = query("SELECT DISTINCT e.id, e.name FROM events e JOIN leads l ON l.event_id = e.id "
                   "JOIN deals d ON d.lead_id = l.id ORDER BY e.start_date DESC")
    return render_template("leads/deals.html", columns=columns, totals=totals, events=events, event_id=event_id)


@bp.route("/deals/<int:deal_id>/stage", methods=["POST"])
@require("deal")
def move_deal(deal_id):
    deal = query("SELECT * FROM deals WHERE id = ?", (deal_id,), one=True)
    stage = request.form.get("stage")
    if deal is None or stage not in refs.DEAL_STAGES:
        abort(404)
    lead = _get_lead(deal["lead_id"])
    close = date.today().isoformat() if stage in ("won", "lost") else None
    db = get_db()
    db.execute("UPDATE deals SET stage = ?, close_date = CASE WHEN ? IS NULL THEN NULL ELSE COALESCE(close_date, ?) END "
               "WHERE id = ?", (stage, close, close, deal_id))
    sync_lead_with_deal(db, lead, stage)
    db.commit()
    flash(f"Угода з {lead['full_name']}: {refs.DEAL_STAGES[stage][0].lower()}.", "success")
    back = request.form.get("back") or url_for("leads.deals")
    return redirect(back if back.startswith("/") and not back.startswith("//") else url_for("leads.deals"))


def _store_lead(event_id, data, source):
    """Збереження ліда, внесеного вручну або з файлу: дата фолоу-апу рахується від сьогодні."""
    data = dict(data)
    data.pop("captured_at", None)
    lead_id = save_lead(event_id, data, g.user["id"])
    execute("UPDATE leads SET source = ? WHERE id = ?", (source, lead_id))
    return lead_id


@bp.route("/events/<int:event_id>/leads/new", methods=["POST"])
@require("lead_import")
def add_lead(event_id):
    """Додавання ліда вручну, наприклад з візитки, яку не встигли внести на події."""
    get_event(event_id)
    source = request.form.get("source") if request.form.get("source") in refs.LEAD_SOURCES else "manual"
    try:
        lead_id = _store_lead(event_id, request.form, source)
        flash("Ліда додано. Дату першого листа визначено за рівнем зацікавленості.", "success")
        return redirect(url_for("leads.detail", lead_id=lead_id))
    except (ValueError, sqlite3.IntegrityError) as e:
        flash(str(e), "danger")
        return redirect(url_for("leads.event_leads", event_id=event_id))


@bp.route("/events/<int:event_id>/leads/import", methods=["POST"])
@require("lead_import")
def import_leads(event_id):
    """Імпорт лідів з файлу (CSV, Excel) або з рядків, вставлених з таблиці."""
    get_event(event_id)
    source = request.form.get("source") if request.form.get("source") in refs.LEAD_SOURCES else "badge_scan"
    upload = request.files.get("file")
    try:
        if upload and upload.filename:
            raw = upload.read()
            if upload.filename.lower().endswith((".xlsx", ".xlsm")):
                rows = importer.rows_from_xlsx(raw)
            else:
                try:
                    text = raw.decode("utf-8-sig")
                except UnicodeDecodeError:
                    text = raw.decode("cp1251", errors="replace")
                rows = importer.rows_from_text(text)
        else:
            rows = importer.rows_from_text(request.form.get("text", ""))
    except Exception:  # пошкоджений файл або не той формат
        flash("Не вдалося прочитати файл. Збережіть таблицю як CSV або Excel (.xlsx) і спробуйте ще раз.", "danger")
        return redirect(url_for("leads.event_leads", event_id=event_id))

    items, skipped = importer.parse_leads(rows)
    existing = {((r["full_name"] or "").lower(), (r["company"] or "").lower())
                for r in query("SELECT full_name, company FROM leads WHERE event_id = ?", (event_id,))}
    owner = request.form.get("owner_id")
    added = dup = 0
    for item in items:
        key = (item["full_name"].lower(), (item["company"] or "").lower())
        if key in existing:
            dup += 1
            continue
        existing.add(key)
        item["owner_id"] = owner
        _store_lead(event_id, item, source)
        added += 1
    parts = [f"Імпортовано лідів: {added}."]
    if dup:
        parts.append(f"Уже були в списку: {dup}.")
    if skipped:
        parts.append(f"Пропущено рядків без імені: {skipped}.")
    flash(" ".join(parts), "success" if added else "warning")
    return redirect(url_for("leads.event_leads", event_id=event_id))


@bp.route("/leads/import-template.csv")
def import_template():
    """Зразок файлу для імпорту лідів."""
    text = ("Ім'я та прізвище;Компанія;Посада;E-mail;Телефон;LinkedIn;Зацікавленість;Нотатка\n"
            "Olena Koval;FinPay;CTO;olena@finpay.example;+380501112233;;гарячий;Просила демо на наступному тижні\n"
            "James Smith;NordPay;Head of Payments;james@nordpay.example;;https://www.linkedin.com/in/james-smith;"
            "теплий;Бюджет на наступний рік\n")
    return Response("﻿" + text, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=conferback-leads-template.csv"})
