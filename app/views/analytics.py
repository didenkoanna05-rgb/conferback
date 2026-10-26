"""Блок Б5 і вивантаження: аналітична дошка, звіт про подію, CSV для CRM (ФВ-17…ФВ-20)."""
import csv
import io
import re

from flask import Blueprint, Response, render_template

from .. import refs, stats
from ..auth import require
from ..db import query
from . import get_event

bp = Blueprint("analytics", __name__)


@bp.route("/events/<int:event_id>/dashboard")
@require("analytics")
def dashboard(event_id):
    event = get_event(event_id)
    return render_template("analytics/dashboard.html", event=event, phase=stats.event_phase(event),
                           dash=stats.dashboard(event), tab="dashboard")


@bp.route("/events/<int:event_id>/report")
@require("analytics")
def report(event_id):
    event = get_event(event_id)
    by_category = query(
        "SELECT cc.name, SUM(ci.amount) AS s, COUNT(*) AS n FROM cost_items ci "
        "JOIN cost_categories cc ON cc.id = ci.category_id WHERE ci.event_id = ? "
        "GROUP BY cc.name ORDER BY s DESC", (event_id,))
    deals = query(
        "SELECT d.*, l.full_name, l.company, l.id AS lead_id FROM deals d JOIN leads l ON l.id = d.lead_id "
        "WHERE l.event_id = ? ORDER BY d.stage = 'won' DESC, d.amount DESC", (event_id,))
    return render_template("analytics/report.html", event=event, phase=stats.event_phase(event),
                           by_category=by_category, deals=deals, dash=stats.dashboard(event),
                           score=stats.score_summary(event_id), tab="report")


CSV_COLUMNS = [
    ("full_name", "Ім'я"), ("company", "Компанія"), ("position", "Посада"), ("email", "E-mail"),
    ("phone", "Телефон"), ("icp_fit", "Відповідність профілю (1-3)"), ("intent", "Зацікавленість (1-3)"),
    ("need_topic", "Потреба"), ("details", "Деталі розмови"), ("next_step", "Наступний крок"),
    ("owner_name", "Відповідальний"), ("due_date", "Дата фолоу-апу"), ("status", "Стан"),
    ("planned", "Запланована зустріч"), ("captured_at", "Час розмови"), ("event_name", "Подія"),
]


@bp.route("/events/<int:event_id>/export.csv")
@require("export")
def export_csv(event_id):
    """Вивантаження лідів у CSV (RFC 4180, UTF-8) для імпорту в CRM, ФВ-20, ДВ-07."""
    event = get_event(event_id)
    rows = query(
        "SELECT l.*, u.full_name AS owner_name, e.name AS event_name FROM leads l "
        "JOIN events e ON e.id = l.event_id LEFT JOIN users u ON u.id = l.owner_id "
        "WHERE l.event_id = ? AND l.status != 'no_action' ORDER BY l.captured_at", (event_id,))
    buf = io.StringIO()
    # BOM потрібен, щоб Excel правильно показав кирилицю
    buf.write("﻿")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerow([title for _, title in CSV_COLUMNS])
    for r in rows:
        values = dict(r)
        values["status"] = refs.LEAD_STATUSES[r["status"]][0]
        values["planned"] = "так" if r["target_id"] else "ні"
        writer.writerow(["" if values.get(k) is None else values[k] for k, _ in CSV_COLUMNS])
    slug = re.sub(r"[^A-Za-z0-9]+", "-", event["name"]).strip("-").lower() or f"event-{event_id}"
    return Response(buf.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="leads-{slug}.csv"'})
