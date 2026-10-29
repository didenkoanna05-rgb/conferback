"""Блок Б2: цільовий список контактів і стан листування (ФВ-05…ФВ-07)."""
import csv
import io
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from .. import refs, stats
from ..auth import can, require
from ..db import execute, get_db, query
from . import clean, get_event, parse_int, users_with_role

bp = Blueprint("targets", __name__)

HEADER_WORDS = {"ім'я", "імя", "name", "full name", "піб", "прізвище"}


@bp.route("/events/<int:event_id>/targets")
def index(event_id):
    event = get_event(event_id)
    status = request.args.get("status")
    sql = ("SELECT t.*, u.full_name AS owner_name, "
           "(SELECT COUNT(*) FROM leads l WHERE l.target_id = t.id AND l.met = 1) AS met "
           "FROM targets t LEFT JOIN users u ON u.id = t.owner_id WHERE t.event_id = ?")
    args = [event_id]
    if status in refs.TARGET_STATUSES:
        sql += " AND t.status = ?"
        args.append(status)
    sql += " ORDER BY t.priority, t.full_name"
    return render_template(
        "targets/index.html", event=event, phase=stats.event_phase(event), targets=query(sql, args),
        counts=stats.target_counts(event_id), status=status, managers=users_with_role("manager"),
        tab="targets")


def _target_data(form):
    source = form.get("source")
    owner = form.get("owner_id")
    channel = form.get("channel")
    meeting_at = (form.get("meeting_at") or "").strip()
    try:
        meeting_at = datetime.fromisoformat(meeting_at).isoformat(timespec="minutes") if meeting_at else None
    except ValueError:
        meeting_at = None
    return {
        "linkedin_url": clean(form.get("linkedin_url"), 300),
        "channel": channel if channel in refs.CHANNELS else "linkedin",
        "priority": parse_int(form.get("priority"), 1, 3) or 2,
        "meeting_at": meeting_at,
        "meeting_place": clean(form.get("meeting_place"), 200),
        "full_name": clean(form.get("full_name"), 200),
        "company": clean(form.get("company"), 200),
        "position": clean(form.get("position"), 200),
        "email": clean(form.get("email"), 200),
        "phone": clean(form.get("phone"), 50),
        "source": source if source in refs.TARGET_SOURCES else "manual",
        "owner_id": int(owner) if owner and owner.isdigit() else None,
        "note": clean(form.get("note"), 1000),
    }


@bp.route("/events/<int:event_id>/targets/new", methods=["POST"])
@require("targets_edit")
def add(event_id):
    get_event(event_id)
    data = _target_data(request.form)
    if not data["full_name"] or not data["company"]:
        flash("Ім'я та компанія обов'язкові.", "danger")
    else:
        data["event_id"] = event_id
        data["status"] = "meeting" if data["meeting_at"] else "candidate"
        execute("INSERT INTO targets (event_id, full_name, company, position, email, phone, linkedin_url, channel, "
                "priority, source, status, owner_id, meeting_at, meeting_place, note) "
                "VALUES (:event_id, :full_name, :company, :position, :email, :phone, :linkedin_url, :channel, "
                ":priority, :source, :status, :owner_id, :meeting_at, :meeting_place, :note)", data)
        flash(f"Контакт {data['full_name']} додано до списку.", "success")
    return redirect(url_for("targets.index", event_id=event_id))


def parse_participants(text):
    """Розбір переліку учасників: ім'я, компанія, посада, контакт (ФВ-06).

    Розділювач визначається автоматично (кома, крапка з комою, табуляція),
    тому дані можна вставити просто з електронної таблиці. Рядки без імені
    чи компанії пропускаються, а імпорт триває далі.
    """
    text = text.lstrip("﻿")
    sample = text[:2000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,\t")
    except csv.Error:
        dialect = csv.excel
    rows, skipped = [], 0
    for i, row in enumerate(csv.reader(io.StringIO(text), dialect)):
        cells = [c.strip() for c in row]
        if not any(cells):
            continue
        if i == 0 and cells[0].lower() in HEADER_WORDS:
            continue
        cells += [""] * (4 - len(cells))
        name, company, position, contact = cells[:4]
        if not name or not company:
            skipped += 1
            continue
        rows.append({
            "full_name": name[:200], "company": company[:200], "position": position[:200] or None,
            "email": contact if "@" in contact else None,
            "linkedin_url": contact if "linkedin.com" in contact else None,
            "phone": contact if contact and "@" not in contact and "linkedin.com" not in contact else None,
        })
    return rows, skipped


@bp.route("/events/<int:event_id>/targets/import", methods=["POST"])
@require("targets_edit")
def import_list(event_id):
    get_event(event_id)
    text = request.form.get("text", "")
    upload = request.files.get("file")
    if upload and upload.filename:
        raw = upload.read()
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("cp1251", errors="replace")
    source = request.form.get("source")
    source = source if source in refs.TARGET_SOURCES else "import"
    rows, skipped = parse_participants(text)
    db = get_db()
    existing = {(r["full_name"].lower(), r["company"].lower())
                for r in query("SELECT full_name, company FROM targets WHERE event_id = ?", (event_id,))}
    added = dup = 0
    for r in rows:
        key = (r["full_name"].lower(), r["company"].lower())
        if key in existing:
            dup += 1
            continue
        existing.add(key)
        channel = "email" if r["email"] else ("event_app" if source == "event_app" else "linkedin")
        db.execute("INSERT INTO targets (event_id, full_name, company, position, email, phone, linkedin_url, channel, source) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   (event_id, r["full_name"], r["company"], r["position"], r["email"], r["phone"], r["linkedin_url"],
                    channel, source))
        added += 1
    db.commit()
    msg = f"Імпортовано контактів: {added}."
    if dup:
        msg += f" Уже були в списку: {dup}."
    if skipped:
        msg += f" Пропущено рядків без імені чи компанії: {skipped}."
    flash(msg, "success" if added else "warning")
    return redirect(url_for("targets.index", event_id=event_id))


@bp.route("/targets/<int:target_id>/status", methods=["POST"])
@require("targets_edit")
def set_status(target_id):
    """Зміна стану листування; дата першого повідомлення записується один раз."""
    target = query("SELECT * FROM targets WHERE id = ?", (target_id,), one=True)
    status = request.form.get("status")
    if target and status in refs.TARGET_STATUSES:
        contacted = date.today().isoformat() if status != "candidate" else None
        execute("UPDATE targets SET status = ?, contacted_at = COALESCE(contacted_at, ?) WHERE id = ?",
                (status, contacted, target_id))
    back = request.form.get("back") or url_for("targets.index", event_id=target["event_id"] if target else 0)
    return redirect(back if back.startswith("/") else "/")


@bp.route("/targets/<int:target_id>/delete", methods=["POST"])
@require("targets_edit")
def delete(target_id):
    """Вилучення контакту зі списку до події. Лід, якщо його вже створено, лишається."""
    target = query("SELECT * FROM targets WHERE id = ?", (target_id,), one=True)
    if target is None:
        abort(404)
    execute("DELETE FROM targets WHERE id = ?", (target_id,))
    flash(f"Контакт {target['full_name']} вилучено зі списку.", "success")
    back = request.form.get("back") or ""
    return redirect(back if back.startswith("/") else url_for("targets.index", event_id=target["event_id"]))


@bp.route("/targets/<int:target_id>/edit", methods=["GET", "POST"])
@require("targets_edit")
def edit(target_id):
    target = query("SELECT * FROM targets WHERE id = ?", (target_id,), one=True)
    if target is None:
        return redirect(url_for("events.index"))
    event = get_event(target["event_id"])
    if request.method == "POST":
        if request.form.get("action") == "delete":
            execute("DELETE FROM targets WHERE id = ?", (target_id,))
            flash("Контакт вилучено зі списку.", "success")
            return redirect(url_for("targets.index", event_id=event["id"]))
        data = _target_data(request.form)
        if not data["full_name"] or not data["company"]:
            flash("Ім'я та компанія обов'язкові.", "danger")
        else:
            data["id"] = target_id
            execute("UPDATE targets SET full_name = :full_name, company = :company, position = :position, "
                    "email = :email, phone = :phone, linkedin_url = :linkedin_url, channel = :channel, "
                    "priority = :priority, source = :source, owner_id = :owner_id, meeting_at = :meeting_at, "
                    "meeting_place = :meeting_place, note = :note WHERE id = :id", data)
            # Призначений час зустрічі означає, що зустріч домовлено
            if data["meeting_at"] and target["status"] in ("candidate", "contacted", "replied", "no_reply"):
                execute("UPDATE targets SET status = 'meeting', contacted_at = COALESCE(contacted_at, ?) WHERE id = ?",
                        (date.today().isoformat(), target_id))
            flash("Зміни збережено.", "success")
            return redirect(url_for("targets.index", event_id=event["id"]))
    leads = query("SELECT id, captured_at, intent, met FROM leads WHERE target_id = ?", (target_id,))
    return render_template("targets/edit.html", event=event, target=target, leads=leads,
                           managers=users_with_role("manager"), can_edit=can("targets_edit"))


DAY_HOURS = range(8, 20)


@bp.route("/events/<int:event_id>/meetings", methods=["GET", "POST"])
def meetings(event_id):
    """Календар домовлених зустрічей: дні події та погодинні слоти."""
    event = get_event(event_id)
    if request.method == "POST":
        if not can("targets_edit"):
            abort(403)
        target_id = parse_int(request.form.get("target_id"), 1, 10**12)
        target = query("SELECT * FROM targets WHERE id = ? AND event_id = ?", (target_id, event_id), one=True)
        day, hour = request.form.get("day"), request.form.get("time")
        try:
            when = datetime.fromisoformat(f"{day}T{hour}")
        except (TypeError, ValueError):
            when = None
        if target is None or when is None:
            flash("Оберіть контакт, день і час.", "danger")
        else:
            execute("UPDATE targets SET meeting_at = ?, meeting_place = COALESCE(?, meeting_place), "
                    "status = CASE WHEN status = 'met' THEN 'met' ELSE 'meeting' END, "
                    "contacted_at = COALESCE(contacted_at, ?) WHERE id = ?",
                    (when.isoformat(timespec="minutes"), clean(request.form.get("place"), 200),
                     date.today().isoformat(), target["id"]))
            flash(f"Зустріч з {target['full_name']} призначено на {when.strftime('%d.%m %H:%M')}.", "success")
        return redirect(url_for("targets.meetings", event_id=event_id))

    rows = query(
        "SELECT t.*, u.full_name AS owner_name FROM targets t LEFT JOIN users u ON u.id = t.owner_id "
        "WHERE t.event_id = ? AND (t.status IN ('meeting', 'met') OR t.meeting_at IS NOT NULL) "
        "ORDER BY t.meeting_at", (event_id,))
    start = date.fromisoformat(event["start_date"])
    end = date.fromisoformat(event["end_date"])
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    grid = {d.isoformat(): {h: [] for h in DAY_HOURS} for d in days}
    unscheduled, outside = [], []
    for r in rows:
        if not r["meeting_at"]:
            unscheduled.append(r)
            continue
        dt = datetime.fromisoformat(r["meeting_at"])
        slot = grid.get(dt.date().isoformat(), {}).get(dt.hour)
        (slot if slot is not None else outside).append(r)
    candidates = query(
        "SELECT id, full_name, company, status, priority FROM targets WHERE event_id = ? "
        "AND status NOT IN ('not_interested') ORDER BY status != 'meeting', priority, full_name", (event_id,))
    return render_template(
        "targets/meetings.html", event=event, phase=stats.event_phase(event), days=days, hours=DAY_HOURS,
        grid=grid, unscheduled=unscheduled, outside=outside, total=len(rows), candidates=candidates,
        tab="meetings")
