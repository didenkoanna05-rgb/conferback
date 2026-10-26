"""Зведені показники кампанії (блок Б5): витрати, дохід, окупність, показники етапів."""
from datetime import date

from . import calc, refs
from .db import query


def event_phase(event, today=None):
    """Стан події за датами: заплановано, триває, завершено."""
    today = (today or date.today()).isoformat()
    if event["start_date"] > today:
        return "planned"
    if event["end_date"] < today:
        return "finished"
    return "ongoing"




def total_cost(event_id):
    """Загальні витрати на подію, ФВ-03."""
    row = query("SELECT COALESCE(SUM(amount), 0) AS s FROM cost_items WHERE event_id = ?", (event_id,), one=True)
    return row["s"]


def revenue_split(event_id):
    """Дохід від укладених угод за типами: нові ліди і прискорені угоди."""
    rows = query(
        "SELECT d.revenue_type, COALESCE(SUM(d.amount), 0) AS s, COUNT(*) AS n "
        "FROM deals d JOIN leads l ON l.id = d.lead_id "
        "WHERE l.event_id = ? AND d.stage = 'won' GROUP BY d.revenue_type",
        (event_id,),
    )
    result = {"new": 0.0, "accelerated": 0.0, "deals": 0}
    for r in rows:
        result[r["revenue_type"]] = r["s"]
        result["deals"] += r["n"]
    return result


def roi_summary(event_id):
    """Окупність події за формулою (3.1) з текстовим висновком, ФВ-17."""
    cost = total_cost(event_id)
    rev = revenue_split(event_id)
    value = calc.roi(rev["new"], rev["accelerated"], cost)
    verdict, tone = calc.roi_verdict(value)
    return {
        "cost": cost,
        "revenue_new": rev["new"],
        "revenue_accelerated": rev["accelerated"],
        "revenue": rev["new"] + rev["accelerated"],
        "deals": rev["deals"],
        "roi": value,
        "verdict": verdict,
        "tone": tone,
    }


def score_summary(event_id):
    """Оцінка доцільності: сума балів, пороги і рекомендація, ФВ-04."""
    criteria = query(
        "SELECT c.id, c.name, c.hint, s.score FROM criteria c "
        "LEFT JOIN event_scores s ON s.criterion_id = c.id AND s.event_id = ? "
        "WHERE c.is_active = 1 ORDER BY c.sort_order, c.id",
        (event_id,),
    )
    n = len(criteria)
    scored = [c["score"] for c in criteria if c["score"] is not None]
    total = sum(scored)
    high, low, maximum = calc.score_thresholds(n)
    complete = n > 0 and len(scored) == n
    return {
        "criteria": criteria,
        "n": n,
        "scored": len(scored),
        "total": total,
        "max": maximum,
        "high": high,
        "low": low,
        "average": (total / len(scored)) if scored else None,
        "complete": complete,
        "verdict": calc.score_verdict(total, n) if complete else None,
    }


def target_counts(event_id):
    counts = {k: 0 for k in refs.TARGET_STATUSES}
    for r in query("SELECT status, COUNT(*) AS n FROM targets WHERE event_id = ? GROUP BY status", (event_id,)):
        counts[r["status"]] = r["n"]
    return counts


def dashboard(event, today=None):
    """Показники трьох етапів кампанії для аналітичної дошки, ФВ-18."""
    eid = event["id"]
    tc = target_counts(eid)
    total_targets = sum(tc.values())
    contacted = total_targets - tc["candidate"]
    responded = tc["replied"] + tc["confirmed"] + tc["meeting"] + tc["declined"]

    leads = query("SELECT target_id, icp_fit, intent, status FROM leads WHERE event_id = ?", (eid,))
    planned = sum(1 for l in leads if l["target_id"])
    qualified = sum(1 for l in leads if calc.is_qualified(l["icp_fit"], l["status"]))
    by_intent = {i: sum(1 for l in leads if l["intent"] == i) for i in (3, 2, 1)}
    by_status = {k: sum(1 for l in leads if l["status"] == k) for k in refs.LEAD_STATUSES}

    fu = query(
        "SELECT COUNT(*) AS n, COUNT(DISTINCT f.lead_id) AS leads FROM followups f "
        "JOIN leads l ON l.id = f.lead_id WHERE l.event_id = ?", (eid,), one=True)
    today_iso = (today or date.today()).isoformat()
    overdue = query(
        "SELECT COUNT(*) AS n FROM leads WHERE event_id = ? AND status IN ('new','in_progress') "
        "AND due_date < ?", (eid, today_iso), one=True)["n"]
    open_deals = query(
        "SELECT COUNT(*) AS n, COALESCE(SUM(d.amount), 0) AS s FROM deals d JOIN leads l ON l.id = d.lead_id "
        "WHERE l.event_id = ? AND d.stage = 'open'", (eid,), one=True)

    roi = roi_summary(eid)
    meetings_set = tc["meeting"]
    met = query(
        "SELECT COUNT(DISTINCT l.target_id) AS n FROM leads l JOIN targets t ON t.id = l.target_id "
        "WHERE l.event_id = ? AND t.status = 'meeting'", (eid,), one=True)["n"]
    return {
        "targets": tc,
        "targets_total": total_targets,
        "contacted": contacted,
        "responded": responded,
        "reply_rate": (responded / contacted) if contacted else None,
        "leads_total": len(leads),
        "planned": planned,
        "spontaneous": len(leads) - planned,
        "planned_share": (planned / len(leads)) if leads else None,
        "meetings_held": met,
        "meetings_set": meetings_set,
        "qualified": qualified,
        "by_intent": by_intent,
        "by_status": by_status,
        "followups": fu["n"],
        "followed_leads": fu["leads"],
        "overdue": overdue,
        "open_deals": open_deals["n"],
        "pipeline": open_deals["s"],
        "cost_per_qualified": (roi["cost"] / qualified) if qualified and roi["cost"] else None,
        "forecast": calc.forecast(meetings_set, event["close_rate"], event["avg_deal"], roi["cost"]),
        "roi": roi,
    }


def event_cards(today=None):
    """Дані для карток на головному екрані."""
    events = query("SELECT * FROM events ORDER BY start_date DESC")
    cards = []
    for e in events:
        leads = query("SELECT COUNT(*) AS n FROM leads WHERE event_id = ?", (e["id"],), one=True)["n"]
        targets = query("SELECT COUNT(*) AS n FROM targets WHERE event_id = ?", (e["id"],), one=True)["n"]
        cards.append({
            "event": e,
            "phase": event_phase(e, today),
            "leads": leads,
            "targets": targets,
            "roi": roi_summary(e["id"]),
            "score": score_summary(e["id"]),
        })
    return cards
