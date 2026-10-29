"""Зведені показники кампанії (блок Б5): витрати, дохід, окупність, статистика етапів."""
from collections import Counter
from datetime import date

from . import calc, refs
from .db import query

# Сума позиції кошторису: фактична, якщо вже внесена, інакше планова
COST_SQL = "COALESCE(actual, planned)"



def event_phase(event, today=None):
    """Стан події за датами: заплановано, триває, завершено."""
    today = (today or date.today()).isoformat()
    if event["start_date"] > today:
        return "planned"
    if event["end_date"] < today:
        return "finished"
    return "ongoing"


def event_status(event, today=None):
    """Статус для користувача: запланована, в роботі, завершена.

    Минула подія лишається «в роботі», доки є ліди, яким ще треба написати,
    або угоди на етапі переговорів.
    """
    phase = event_phase(event, today)
    if phase == "planned":
        return "planned"
    if phase == "ongoing":
        return "in_work"
    open_work = query(
        "SELECT 1 FROM leads l LEFT JOIN deals d ON d.lead_id = l.id WHERE l.event_id = ? "
        "AND (l.status IN ('new', 'in_progress') OR d.stage IN ('negotiation', 'proposal')) LIMIT 1",
        (event["id"],), one=True)
    return "in_work" if open_work else "done"


def cost_totals(event_id):
    """Витрати на подію: план, факт і сума для розрахунку окупності (ФВ-03)."""
    row = query(
        f"SELECT COALESCE(SUM(planned), 0) AS planned, COALESCE(SUM(actual), 0) AS actual, "
        f"COUNT(actual) AS with_actual, COUNT(*) AS items, COALESCE(SUM({COST_SQL}), 0) AS total "
        "FROM cost_items WHERE event_id = ?", (event_id,), one=True)
    return dict(row)


def total_cost(event_id):
    return cost_totals(event_id)["total"]


def costs_by_category(event_id):
    return query(
        "SELECT cc.name, SUM(ci.planned) AS planned, SUM(ci.actual) AS actual, "
        "SUM(COALESCE(ci.actual, ci.planned)) AS total "
        "FROM cost_items ci JOIN cost_categories cc ON cc.id = ci.category_id WHERE ci.event_id = ? "
        "GROUP BY cc.name ORDER BY total DESC", (event_id,))


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
    costs = cost_totals(event_id)
    rev = revenue_split(event_id)
    value = calc.roi(rev["new"], rev["accelerated"], costs["total"])
    verdict, tone = calc.roi_verdict(value)
    return {
        "cost": costs["total"],
        "cost_planned": costs["planned"],
        "cost_actual": costs["actual"],
        "cost_is_final": costs["items"] > 0 and costs["with_actual"] == costs["items"],
        "revenue_new": rev["new"],
        "revenue_accelerated": rev["accelerated"],
        "revenue": rev["new"] + rev["accelerated"],
        "deals": rev["deals"],
        "roi": value,
        "status": calc.roi_status(value),
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
    """Показники трьох етапів кампанії для вікна статистики, ФВ-18."""
    eid = event["id"]
    tc = target_counts(eid)
    total_targets = sum(tc.values())
    contacted = total_targets - tc["candidate"]
    responded = tc["replied"] + tc["meeting"] + tc["met"] + tc["not_interested"]
    meetings_set = tc["meeting"] + tc["met"]
    targets = query("SELECT channel, priority, status FROM targets WHERE event_id = ?", (eid,))
    target_channels = Counter(t["channel"] for t in targets if t["status"] != "candidate")
    replied_channels = Counter(t["channel"] for t in targets
                               if t["status"] in ("replied", "meeting", "met", "not_interested"))

    leads = query("SELECT target_id, met, icp_fit, intent, status, channel, captured_at FROM leads WHERE event_id = ?",
                  (eid,))
    met_leads = [l for l in leads if l["met"]]
    planned = sum(1 for l in met_leads if l["target_id"])
    qualified = sum(1 for l in met_leads if calc.is_qualified(l["icp_fit"], l["status"]))
    by_intent = {i: sum(1 for l in met_leads if l["intent"] == i) for i in (3, 2, 1)}
    by_status = {k: sum(1 for l in leads if l["status"] == k) for k in refs.LEAD_STATUSES}
    by_day = Counter(l["captured_at"][:10] for l in met_leads)
    by_icp = {i: sum(1 for l in met_leads if l["icp_fit"] == i) for i in (3, 2, 1)}

    fu = query(
        "SELECT COUNT(*) AS n, COUNT(DISTINCT f.lead_id) AS leads FROM followups f "
        "JOIN leads l ON l.id = f.lead_id WHERE l.event_id = ?", (eid,), one=True)
    fu_channels = Counter(r["channel"] for r in query(
        "SELECT f.channel FROM followups f JOIN leads l ON l.id = f.lead_id WHERE l.event_id = ?", (eid,)))
    today_iso = (today or date.today()).isoformat()
    overdue = query(
        "SELECT COUNT(*) AS n FROM leads WHERE event_id = ? AND status IN ('new','in_progress') "
        "AND due_date < ?", (eid, today_iso), one=True)["n"]
    open_deals = query(
        "SELECT COUNT(*) AS n, COALESCE(SUM(d.amount), 0) AS s FROM deals d JOIN leads l ON l.id = d.lead_id "
        "WHERE l.event_id = ? AND d.stage IN ('negotiation', 'proposal')", (eid,), one=True)

    roi = roi_summary(eid)
    return {
        "targets": tc,
        "targets_total": total_targets,
        "contacted": contacted,
        "responded": responded,
        "reply_rate": (responded / contacted) if contacted else None,
        "target_channels": target_channels,
        "replied_channels": replied_channels,
        "priorities": Counter(t["priority"] for t in targets),
        "leads_total": len(met_leads),
        "unmet_in_work": len(leads) - len(met_leads),
        "planned": planned,
        "spontaneous": len(met_leads) - planned,
        "planned_share": (planned / len(met_leads)) if met_leads else None,
        "meetings_held": tc["met"],
        "meetings_set": meetings_set,
        "meeting_rate": (tc["met"] / meetings_set) if meetings_set else None,
        "qualified": qualified,
        "qualified_share": (qualified / len(met_leads)) if met_leads else None,
        "by_intent": by_intent,
        "by_icp": by_icp,
        "by_status": by_status,
        "by_day": sorted(by_day.items()),
        "followups": fu["n"],
        "followed_leads": fu["leads"],
        "followup_channels": fu_channels,
        "overdue": overdue,
        "open_deals": open_deals["n"],
        "pipeline": open_deals["s"],
        "cost_per_lead": (roi["cost"] / len(met_leads)) if met_leads and roi["cost"] else None,
        "cost_per_qualified": (roi["cost"] / qualified) if qualified and roi["cost"] else None,
        "forecast": calc.forecast(meetings_set, event["close_rate"], event["avg_deal"], roi["cost"]),
        "roi": roi,
    }


def event_cards(today=None):
    """Дані для карток на головному екрані."""
    events = query("SELECT * FROM events ORDER BY start_date DESC")
    cards = []
    for e in events:
        leads = query("SELECT COUNT(*) AS n FROM leads WHERE event_id = ? AND met = 1", (e["id"],), one=True)["n"]
        targets = query("SELECT COUNT(*) AS n FROM targets WHERE event_id = ?", (e["id"],), one=True)["n"]
        meetings = query("SELECT COUNT(*) AS n FROM targets WHERE event_id = ? AND status IN ('meeting', 'met')",
                         (e["id"],), one=True)["n"]
        score = score_summary(e["id"])
        status = event_status(e, today)
        roi = roi_summary(e["id"])
        cards.append({
            "event": e,
            "phase": event_phase(e, today),
            "status": status,
            "recommendation": (score["verdict"]["code"] if score["verdict"] else "none"),
            # Окупність має сенс лише для подій, що вже відбулися
            "roi_status": roi["status"] if status != "planned" else None,
            "leads": leads,
            "targets": targets,
            "meetings": meetings,
            "roi": roi,
            "score": score,
        })
    return cards
