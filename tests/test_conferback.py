"""Автоматичні тести: формули (3.1)–(3.4), синхронізація без мережі, ролі, імпорт."""
import re
from datetime import date

import pytest

from app import calc, create_app
from app.db import create_user
from app.views.targets import parse_participants


# ---------- Формули ----------

def test_followup_date_by_intent():
    d = date(2026, 6, 3)
    assert calc.followup_date(3, d) == d
    assert calc.followup_date(2, d) == date(2026, 6, 5)
    assert calc.followup_date(1, d) == date(2026, 6, 17)


def test_roi_control_example():
    # Контрольний приклад Money20/20: (86 000 + 49 000) / 27 300 = 4,95
    value = calc.roi(86000, 49000, 27300)
    assert round(value, 2) == 4.95
    assert calc.roi_status(value) == "norm"


@pytest.mark.parametrize("value, code", [
    (0.5, "loss"),
    (1.0, "low"),
    (3.0, "norm"),
    (5.1, "high"),
    (None, "none"),
])
def test_roi_bands(value, code):
    assert calc.roi_status(value) == code


def test_roi_without_costs():
    assert calc.roi(1000, 0, 0) is None


def test_score_thresholds_scale_with_criteria():
    assert calc.score_verdict(31, 8)["code"] == "go"       # 31 ≥ 28
    assert calc.score_verdict(27, 8)["code"] == "review"   # 20 ≤ 27 < 28
    assert calc.score_verdict(18, 8)["code"] == "no"       # 18 < 20
    assert calc.score_thresholds(10)[:2] == (35, 25)       # новий критерій без зміни коду


def test_forecast():
    assert calc.forecast(8, 0.2, 25000, 14000) == 26000
    assert calc.forecast(8, None, 25000, 14000) is None


def test_split_queue():
    leads = [{"due_date": "2026-10-20"}, {"due_date": "2026-10-26"}, {"due_date": "2026-11-01"}]
    g = calc.split_queue(leads, date(2026, 10, 26))
    assert [len(g[k]) for k in ("overdue", "today", "upcoming")] == [1, 1, 1]


def test_parse_participants_skips_bad_rows():
    text = "Ім'я;Компанія;Посада;Контакт\nOlena;FinPay;CTO;o@finpay.example\n;NoName;;\nIvan;Bank;;https://linkedin.com/in/ivan\n"
    rows, skipped = parse_participants(text)
    assert [r["full_name"] for r in rows] == ["Olena", "Ivan"]
    assert rows[0]["email"] == "o@finpay.example"
    assert rows[1]["linkedin_url"].startswith("https://linkedin.com")
    assert skipped == 1


# ---------- Вебзастосунок ----------

@pytest.fixture
def app(tmp_path):
    app = create_app({"DATABASE": str(tmp_path / "test.sqlite"), "SECRET_KEY": "test", "DEMO_LOGINS": None})
    with app.app_context():
        create_user("rep", "Rep", "password1", ["rep"])
        create_user("head", "Head", "password1", ["head"])
        from app.db import execute
        execute("INSERT INTO events (name, start_date, end_date) VALUES ('Test', '2026-11-09', '2026-11-12')")
        execute("INSERT INTO targets (event_id, full_name, company, channel) VALUES (1, 'Olena', 'FinPay', 'email')")
    return app


def login(app, username):
    c = app.test_client()
    token = re.search(rb'name="csrf_token" value="([^"]+)"', c.get("/login").data).group(1).decode()
    c.post("/login", data={"username": username, "password": "password1", "csrf_token": token})
    return c


def page_token(c, url):
    return re.search(rb'name="csrf_token" value="([^"]+)"', c.get(url).data).group(1).decode()


def test_login_required(app):
    assert app.test_client().get("/").status_code == 302


def test_post_without_csrf_rejected(app):
    c = login(app, "head")
    assert c.post("/events/1/score", data={}).status_code == 400


def test_roles_restrict_actions(app):
    rep = login(app, "rep")
    assert rep.get("/events/1/dashboard").status_code == 403
    assert rep.get("/events/1/capture").status_code == 200
    head = login(app, "head")
    assert head.get("/events/1/dashboard").status_code == 200
    assert head.get("/events/1/capture").status_code == 403


def test_sync_is_idempotent_and_tolerates_bad_records(app):
    c = login(app, "rep")
    token = page_token(c, "/events/1/capture")
    batch = {"leads": [
        {"event_id": 1, "full_name": "Ivan", "intent": "3", "client_uid": "u1", "captured_at": "2026-11-10T11:00:00"},
        {"event_id": 1, "intent": "2", "client_uid": "u2"},                     # без імені
        {"event_id": 1, "target_id": 1, "intent": "2", "client_uid": "u3"},     # ім'я з цільового списку
    ]}
    first = c.post("/api/sync", json=batch, headers={"X-CSRF-Token": token}).get_json()
    assert (first["saved"], first["rejected"]) == (2, 1)
    assert set(first["done"]) == {"u1", "u3"}
    second = c.post("/api/sync", json=batch, headers={"X-CSRF-Token": token}).get_json()
    assert (second["saved"], second["skipped"]) == (0, 2)
    with app.app_context():
        from app.db import query
        hot = query("SELECT due_date FROM leads WHERE client_uid = 'u1'", one=True)
        assert hot["due_date"] == "2026-11-10"   # гарячий лід — фолоу-ап того ж дня
        assert query("SELECT status FROM targets WHERE id = 1", one=True)["status"] == "met"
        assert query("SELECT channel FROM leads WHERE client_uid = 'u3'", one=True)["channel"] == "email"


def test_import_leads_with_header():
    from app import importer
    rows = importer.rows_from_text(
        "First Name,Last Name,Company Name,Job Title,Email Address,Lead Rating,Notes\n"
        "Olena,Koval,FinPay,CTO,olena@finpay.example,Hot,Demo please\n"
        ",,NoName Ltd,,,,\n")
    leads, skipped = importer.parse_leads(rows)
    assert skipped == 1
    assert leads[0]["full_name"] == "Olena Koval"
    assert leads[0]["company"] == "FinPay" and leads[0]["intent"] == 3 and leads[0]["channel"] == "email"


def test_import_leads_without_header():
    from app import importer
    leads, _ = importer.parse_leads(importer.rows_from_text("James Smith;NordPay;CIO;https://linkedin.com/in/js\n"))
    assert leads[0]["linkedin_url"] == "https://linkedin.com/in/js" and leads[0]["intent"] == 2
    assert leads[0]["channel"] == "linkedin"


@pytest.mark.parametrize("url", ["/", "/events/new", "/events/1", "/events/1/edit", "/events/1/costs",
                                 "/events/1/targets", "/events/1/meetings", "/events/1/leads", "/events/1/dashboard",
                                 "/events/1/report", "/formulas", "/queue", "/deals", "/stats", "/settings"])
def test_pages_open(app, url):
    # Кожна сторінка відкривається без помилки сервера
    assert login(app, "head").get(url).status_code == 200


def test_delete_target_and_lead(app):
    c = login(app, "head")
    token = page_token(c, "/events/1/leads")
    c.post("/events/1/leads/new", data={"csrf_token": token, "full_name": "Ivan Test", "intent": "2"})
    with app.app_context():
        from app.db import query
        lead_id = query("SELECT id FROM leads WHERE full_name = 'Ivan Test'", one=True)["id"]
    assert c.post(f"/leads/{lead_id}/delete", data={"csrf_token": token}).status_code == 302
    assert c.post("/targets/1/delete", data={"csrf_token": token}).status_code == 302
    with app.app_context():
        from app.db import query
        assert query("SELECT COUNT(*) AS n FROM leads", one=True)["n"] == 0
        assert query("SELECT COUNT(*) AS n FROM targets", one=True)["n"] == 0
    # Представник на заході не може вилучати
    rep = login(app, "rep")
    assert rep.post("/targets/1/delete", data={"csrf_token": page_token(rep, "/")}).status_code == 403
