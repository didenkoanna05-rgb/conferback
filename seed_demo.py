"""Заповнення бази демонстраційними даними (контрольний приклад).

Назви й міста заходів відповідають реальним конференціям, дати орієнтовні,
а суми, імена та назви компаній вигадані.

Запуск:  python seed_demo.py          (база створюється заново!)
"""
import json
import os
import random
import sys
from datetime import date, datetime, timedelta

from app import create_app
from app.calc import followup_date
from app.db import create_user, get_db, init_db

PASSWORD = "demo2026"
rnd = random.Random(2026)

USERS = [
    ("head", "Олег Коваленко", ["head"]),
    ("marketer", "Ірина Марченко", ["marketer"]),
    ("manager", "Андрій Шевчук", ["manager"]),
    ("manager2", "Марія Бондар", ["manager", "rep"]),
    ("rep", "Тарас Лисенко", ["rep"]),
]
DEMO_LOGINS = [
    ("head", "Керівник продажів"),
    ("marketer", "Маркетолог"),
    ("manager", "Менеджер з продажу"),
    ("rep", "Представник на заході"),
]

FIRST = ["Anna", "James", "Sofia", "Lukas", "Emma", "Oliver", "Marta", "Daniel", "Laura", "Pieter", "Chloé",
         "Marco", "Eva", "Tomasz", "Nina", "Henrik", "Clara", "Jonas", "Elena", "David", "Ines", "Mateo",
         "Olena", "Dmytro", "Kateryna", "Yuriy", "Sarah", "Michael", "Julia", "Stefan", "Hanna", "Andrés"]
LAST = ["Müller", "Smith", "Rossi", "de Vries", "Novak", "Johansson", "García", "Kowalski", "Dubois",
        "Schmidt", "Bianchi", "Jansen", "Horvat", "Nielsen", "Ferreira", "Brown", "Weber", "Moreau",
        "Lindqvist", "Petrenko", "Shevchenko", "Kovacs", "Fischer", "Costa", "Wilson", "Becker"]
COMPANIES = ["NordPay", "Brightlane Bank", "Veritas Retail", "Lumen Logistics", "Quantis Insurance",
             "Helio Telecom", "Arcadia Health", "Finova", "Bluepeak Energy", "Stratus Media", "Kronos Tech",
             "MetroCredit", "Atlas Freight", "Corvid Security", "PayHub", "Orbis Travel", "Nimbus Cloud",
             "Vantage Capital", "Delta Markets", "Ember Foods", "Polar Systems", "Granite Group",
             "Silverline AG", "Monarch Software", "Tidewater Ports", "Zenith Mobility"]
POSITIONS = ["CTO", "Head of IT", "CIO", "Head of Payments", "Product Director", "CISO", "VP Engineering",
             "Head of Digital", "COO", "IT Manager", "Procurement Lead", "Head of Data"]
DETAILS = [
    "Шукають заміну застарілій системі до кінця кварталу, бюджет уже затверджено.",
    "Цікавить пілот на одному підрозділі, рішення ухвалює рада директорів.",
    "Порівнюють нас із двома конкурентами, просили кейси з банківського сектору.",
    "Мають проблему з інтеграцією CRM, готові до дзвінка наступного тижня.",
    "Поки збирають інформацію, бюджет на наступний рік.",
    "Просили комерційну пропозицію з розбивкою за етапами.",
    "Зацікавила аналітика, хочуть демо для своєї команди.",
    "Невелика компанія, але швидко ухвалюють рішення.",
]
TOPICS = ["Автоматизація процесів", "Інтеграція систем", "Безпека даних", "Аналітика та звітність",
          "Платіжні рішення", "Розроблення на замовлення"]
STEPS = ["Надіслати матеріали", "Призначити дзвінок", "Демонстрація продукту", "Комерційна пропозиція"]

EVENTS = [
    {
        "name": "Tech Show London 2026", "city": "Лондон", "address": "ExCeL London, 1 Western Gateway, Royal Victoria Dock", "start": "2026-03-04", "end": "2026-03-05",
        "booth": 1, "goal": "Перевірити британський ринок: знайти 5 компаній для пілотних проєктів.",
        "costs": [("Реєстраційний внесок", "Стенд 3×3 м", 8000, 8000), ("Переїзд", "Квитки на 3 особи", 3000, 3500),
                  ("Проживання", "Готель, 3 ночі", 2000, 2000), ("Стенд і оформлення", "Банер, освітлення", 1200, 1500),
                  ("Робочий час персоналу", "3 особи × 2 дні", 1200, 1200), ("Матеріали", "Буклети, сувеніри", 1000, 800)],
        "scores": [3, 2, 2, 2, 3, 2, 2, 2],
        "targets": {"contacted": 10, "replied": 12, "meeting": 6, "not_interested": 15, "no_reply": 25},
        "leads": 58, "planned": 9,
        "deals": [("won", "new", 8500)],
        "lost": 2, "open": 0, "active_queue": False,
    },
    {
        "name": "Money20/20 Europe 2026", "city": "Амстердам", "address": "RAI Amsterdam, Europaplein 24", "start": "2026-06-02", "end": "2026-06-04",
        "booth": 1, "goal": "Зустрітися з банками та платіжними компаніями Бенілюксу; закрити дві угоди, що вже в роботі.",
        "costs": [("Реєстраційний внесок", "Участь зі стендом", 12000, 12000), ("Проживання", "Готель, 4 ночі × 3 особи", 4200, 4800),
                  ("Переїзд", "Квитки Київ—Амстердам", 3500, 3800), ("Стенд і оформлення", "Забудова стенда", 3500, 3200),
                  ("Робочий час персоналу", "3 особи × 3 дні", 2600, 2600), ("Матеріали", "Друк, мерч", 1000, 900)],
        "scores": [5, 4, 4, 4, 4, 3, 4, 3],
        "targets": {"candidate": 12, "contacted": 23, "replied": 14, "meeting": 7, "not_interested": 11, "no_reply": 17},
        "leads": 112, "planned": 14,
        "deals": [("won", "new", 42000), ("won", "new", 26000), ("won", "new", 18000),
                  ("won", "accelerated", 31000), ("won", "accelerated", 18000)],
        "lost": 3, "open": 0, "active_queue": False,
    },
    {
        "name": "Black Hat USA 2026", "city": "Лас-Вегас", "address": "Mandalay Bay, 3950 S Las Vegas Blvd", "start": "2026-08-01", "end": "2026-08-06",
        "booth": 0, "goal": "Без стенда: зустрічі з CISO компаній зі списку, пошук партнерів з безпеки.",
        "costs": [("Реєстраційний внесок", "Квитки на 3 особи", 9900, 9900), ("Переїзд", "Переліт", 6000, 6800),
                  ("Проживання", "Готель, 6 ночей", 6000, 6400), ("Робочий час персоналу", "3 особи × 6 днів", 2000, 2000),
                  ("Матеріали", "Візитки, презентації", 600, 800)],
        "scores": [5, 4, 4, 3, 5, 3, 4, 4],
        "targets": {"replied": 13, "meeting": 9, "not_interested": 18, "no_reply": 30},
        "leads": 70, "planned": 15,
        "deals": [("won", "new", 35000)],
        "lost": 1, "open": 4, "active_queue": True, "take_unmet": 12,
    },
    {
        "name": "Web Summit Lisbon 2026", "city": "Лісабон", "address": "MEO Arena і FIL, Rossio dos Olivais", "start": "2026-11-09", "end": "2026-11-12",
        "booth": 1, "goal": "Домовитися про 10 зустрічей заздалегідь; знайти партнерів у Португалії та Іспанії.",
        "costs": [("Реєстраційний внесок", "Стенд Alpha", 6500, 6500), ("Переїзд", "Переліт", 2500, 2350),
                  ("Проживання", "Апартаменти, 4 ночі", 2200, None), ("Робочий час персоналу", "2 особи × 4 дні", 1800, None),
                  ("Матеріали", "Буклети", 600, None), ("Інше", "Транспорт на місці", 400, None)],
        "scores": [5, 4, 3, 3, 5, 4, 4, 4],
        "targets": {"candidate": 12, "contacted": 15, "replied": 12, "meeting": 8, "not_interested": 2, "no_reply": 1},
        "leads": 0, "planned": 0, "close_rate": 0.2, "avg_deal": 25000,
        "deals": [], "lost": 0, "open": 0, "active_queue": False,
    },
    {
        "name": "Slush 2026", "city": "Гельсінкі", "address": "Messukeskus, Messuaukio 1",
        "start": "2026-11-18", "end": "2026-11-19",
        "booth": 0, "goal": "Без стенда: знайти скандинавських партнерів і познайомитися з фінтех-стартапами.",
        "costs": [("Реєстраційний внесок", "Квитки на 2 особи", 1800, None), ("Переїзд", "Переліт", 900, None),
                  ("Проживання", "Готель, 3 ночі", 1100, None), ("Робочий час персоналу", "2 особи × 2 дні", 900, None)],
        "scores": [4, 3, 3, 3, 3, 2, 4, 3],
        "targets": {"candidate": 14, "contacted": 9, "replied": 5, "meeting": 3, "no_reply": 2},
        "leads": 0, "planned": 0, "close_rate": 0.15, "avg_deal": 18000,
        "deals": [], "lost": 0, "open": 0, "active_queue": False,
    },
    {
        "name": "AWS re:Invent 2026", "city": "Лас-Вегас", "address": "The Venetian Expo, 201 Sands Ave",
        "start": "2026-11-30", "end": "2026-12-04",
        "booth": 0, "goal": "Оцінити, чи варто їхати: аудиторія переважно технічна, клієнтів-банків мало.",
        "costs": [("Реєстраційний внесок", "Квитки на 2 особи", 4200, None), ("Переїзд", "Переліт", 4800, None),
                  ("Проживання", "Готель, 5 ночей", 5200, None), ("Робочий час персоналу", "2 особи × 5 днів", 2500, None)],
        "scores": [3, 2, 2, 1, 2, 1, 3, 1],
        "targets": {"candidate": 6, "contacted": 4, "replied": 1},
        "leads": 0, "planned": 0, "close_rate": 0.1, "avg_deal": 20000,
        "deals": [], "lost": 0, "open": 0, "active_queue": False,
    },
    {
        "name": "Black Hat Europe 2026", "city": "Лондон", "address": "ExCeL London, 1 Western Gateway, Royal Victoria Dock",
        "start": "2026-12-08", "end": "2026-12-11",
        "booth": 0, "goal": "Продовжити розмови з CISO європейських банків після Black Hat USA; 8 зустрічей заздалегідь.",
        "costs": [("Реєстраційний внесок", "Квитки на 2 особи", 3600, None), ("Переїзд", "Переліт Київ—Лондон", 1400, None),
                  ("Проживання", "Готель, 4 ночі", 2600, None), ("Робочий час персоналу", "2 особи × 4 дні", 1600, None),
                  ("Матеріали", "Презентації, візитки", 300, None)],
        "scores": [5, 4, 4, 3, 4, 3, 4, 4],
        "targets": {"candidate": 10, "contacted": 12, "replied": 7, "meeting": 6, "not_interested": 3, "no_reply": 4},
        "leads": 0, "planned": 0, "close_rate": 0.2, "avg_deal": 28000,
        "deals": [], "lost": 0, "open": 0, "active_queue": False,
    },
]

SOURCES = ["event_site", "event_app", "linkedin", "own_base", "manual"]
TARGET_CHANNELS = ["linkedin", "email", "event_app", "messenger"]
LEAD_CHANNELS = ["email", "linkedin", "messenger", "phone"]
PLACES = ["Наш стенд", "Кав'ярня біля зали 1", "Лаунж для учасників", "Зона нетворкінгу", "Стенд партнера"]


def linkedin_for(name):
    return "https://www.linkedin.com/in/" + name.lower().replace(" ", "-").replace("é", "e").replace("ü", "u") + "-demo"


def person():
    return f"{rnd.choice(FIRST)} {rnd.choice(LAST)}"


def email_for(name, company):
    first = name.split()[0].lower()
    return f"{first}@{company.lower().replace(' ', '')}.example"


def seed():
    db = get_db()
    ids = {u: create_user(u, n, PASSWORD, roles) for u, n, roles in USERS}
    managers = [ids["manager"], ids["manager2"]]
    reps = [ids["rep"], ids["manager2"]]
    cats = {r["name"]: r["id"] for r in db.execute("SELECT id, name FROM cost_categories")}
    crits = [r["id"] for r in db.execute("SELECT id FROM criteria ORDER BY sort_order")]
    today = date.today()

    for ev in EVENTS:
        eid = db.execute(
            "INSERT INTO events (name, city, address, start_date, end_date, goal, has_booth, close_rate, avg_deal) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (ev["name"], ev["city"], ev.get("address"), ev["start"], ev["end"], ev["goal"], ev["booth"],
             ev.get("close_rate", 0.2), ev.get("avg_deal", 25000))).lastrowid
        for cat, desc, planned, actual in ev["costs"]:
            db.execute("INSERT INTO cost_items (event_id, category_id, description, planned, actual) VALUES (?, ?, ?, ?, ?)",
                       (eid, cats[cat], desc, planned, actual))
        for cid, score in zip(crits, ev["scores"]):
            db.execute("INSERT INTO event_scores (event_id, criterion_id, score) VALUES (?, ?, ?)", (eid, cid, score))

        start = date.fromisoformat(ev["start"])
        end = date.fromisoformat(ev["end"])
        target_rows = []
        for status, count in ev["targets"].items():
            for _ in range(count):
                name, company = person(), rnd.choice(COMPANIES)
                contacted = None if status == "candidate" else (start - timedelta(days=rnd.randint(10, 35))).isoformat()
                meeting_at = place = None
                if status == "meeting":
                    day = start + timedelta(days=rnd.randint(0, (end - start).days))
                    meeting_at = f"{day.isoformat()}T{rnd.randint(9, 17):02d}:{rnd.choice(['00', '30']):s}"
                    place = rnd.choice(PLACES)
                tid = db.execute(
                    "INSERT INTO targets (event_id, full_name, company, position, email, linkedin_url, channel, priority, "
                    "source, status, owner_id, contacted_at, meeting_at, meeting_place) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (eid, name, company, rnd.choice(POSITIONS), email_for(name, company), linkedin_for(name),
                     rnd.choices(TARGET_CHANNELS, weights=[5, 3, 2, 1])[0],
                     1 if status == "meeting" else rnd.choices([1, 2, 3], weights=[2, 5, 3])[0],
                     rnd.choice(SOURCES), status, rnd.choice(managers), contacted, meeting_at, place)).lastrowid
                target_rows.append((tid, name, company, status))

        # Ліди: заплановані зустрічі беремо з тих, хто домовився або підтвердив участь
        planned_pool = [t for t in target_rows if t[3] in ("meeting", "replied")]
        planned_pool.sort(key=lambda t: t[3] != "meeting")
        lead_ids = []
        for i in range(ev["leads"]):
            target = planned_pool[i] if i < min(ev["planned"], len(planned_pool)) else None
            name, company = (target[1], target[2]) if target else (person(), rnd.choice(COMPANIES))
            intent = rnd.choices([3, 2, 1], weights=[2, 4, 4])[0]
            icp = rnd.choices([3, 2, 1], weights=[3, 4, 3])[0]
            day = start + timedelta(days=rnd.randint(0, (end - start).days))
            captured = datetime.combine(day, datetime.min.time()) + timedelta(hours=rnd.randint(9, 17), minutes=rnd.randint(0, 59))
            no_prospect = icp == 1 and intent == 1 and rnd.random() < 0.6
            if target:
                db.execute("UPDATE targets SET status = 'met' WHERE id = ?", (target[0],))
            lid = db.execute(
                "INSERT INTO leads (event_id, target_id, full_name, company, position, email, linkedin_url, channel, "
                "icp_fit, intent, need_topic, details, next_step, owner_id, due_date, captured_at, captured_by, status, "
                "client_uid, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (eid, target[0] if target else None, name, company, rnd.choice(POSITIONS), email_for(name, company),
                 linkedin_for(name), rnd.choices(LEAD_CHANNELS, weights=[5, 4, 2, 1])[0],
                 icp, intent, rnd.choice(TOPICS), rnd.choice(DETAILS), rnd.choice(STEPS), rnd.choice(managers),
                 None if no_prospect else followup_date(intent, day).isoformat(),
                 captured.isoformat(timespec="seconds"), rnd.choice(reps),
                 "no_action" if no_prospect else "new", f"demo-{eid}-{i}",
                 # Частину контактів на стенді зібрали сканером бейджів і завантажили файлом
                 "badge_scan" if ev["booth"] and not target and rnd.random() < 0.25 else None)).lastrowid
            if not no_prospect:
                lead_ids.append((lid, intent, day))

        # Найгарячіші ліди першими отримують угоди
        lead_ids.sort(key=lambda x: (-x[1], x[0]))
        pos = 0
        deal_specs = ev["deals"] + [("lost", "new", rnd.choice([12000, 20000, 9000])) for _ in range(ev["lost"])] \
            + [(rnd.choice(["negotiation", "proposal"]), "new", rnd.choice([15000, 24000, 30000])) for _ in range(ev["open"])]
        for stage, rtype, amount in deal_specs:
            lid, _, day = lead_ids[pos]
            pos += 1
            close = (day + timedelta(days=rnd.randint(25, 70))).isoformat() if stage in ("won", "lost") else None
            db.execute("INSERT INTO deals (lead_id, amount, stage, revenue_type, close_date) VALUES (?, ?, ?, ?, ?)",
                       (lid, amount, stage, rtype, close))
            add_followups(db, lid, day, rnd.randint(2, 3), managers, final="agreement")
            if stage == "won":
                db.execute("UPDATE leads SET status = 'won', due_date = NULL WHERE id = ?", (lid,))
            elif stage == "lost":
                db.execute("UPDATE leads SET status = 'closed', due_date = NULL WHERE id = ?", (lid,))
            else:
                due = today + timedelta(days=rnd.randint(1, 10))
                db.execute("UPDATE leads SET status = 'in_progress', due_date = ? WHERE id = ?", (due.isoformat(), lid))

        # Решта лідів
        for lid, intent, day in lead_ids[pos:]:
            if ev["active_queue"] and rnd.random() < 0.8:
                # Черга ще жива: частина прострочена, частина на сьогодні, частина пізніше
                offset = rnd.choices([-rnd.randint(1, 6), 0, rnd.randint(1, 21)], weights=[2, 2, 6])[0]
                n = rnd.randint(0, 2)
                if n:
                    add_followups(db, lid, day, n, managers)
                db.execute("UPDATE leads SET status = ?, due_date = ? WHERE id = ?",
                           ("in_progress" if n else "new", (today + timedelta(days=offset)).isoformat(), lid))
            else:
                add_followups(db, lid, day, rnd.randint(1, 3), managers, final="refused")
                db.execute("UPDATE leads SET status = 'closed', due_date = NULL WHERE id = ?", (lid,))
        # Контакти зі списку, з якими не зустрілися, але після події взяли в роботу
        unmet = [t for t in target_rows if t[3] in ("replied", "meeting", "no_reply")
                 and not db.execute("SELECT 1 FROM leads WHERE target_id = ?", (t[0],)).fetchone()]
        for tid, name, company, _ in unmet[:ev.get("take_unmet", 0)]:
            db.execute(
                "INSERT INTO leads (event_id, target_id, full_name, company, email, linkedin_url, channel, met, owner_id, "
                "due_date, captured_at, captured_by, status, next_step, client_uid) "
                "VALUES (?, ?, ?, ?, ?, ?, 'linkedin', 0, ?, ?, ?, ?, 'new', ?, ?)",
                (eid, tid, name, company, email_for(name, company), linkedin_for(name), rnd.choice(managers),
                 (today + timedelta(days=rnd.randint(-2, 5))).isoformat(),
                 datetime.combine(end + timedelta(days=1), datetime.min.time()).isoformat(timespec="seconds"),
                 rnd.choice(managers), "Лист «шкода, що не зустрілися»", f"unmet-{tid}"))
    spread_queue(db, managers, today)
    db.commit()


def spread_queue(db, managers, today):
    """Черга дій як у робочій системі: на кожен день від трьох днів тому до трьох тижнів уперед
    є завдання в обох менеджерів, а сьогодні — найбільше."""
    open_leads = [r[0] for r in db.execute(
        "SELECT l.id FROM leads l LEFT JOIN deals d ON d.lead_id = l.id "
        "WHERE l.status IN ('new', 'in_progress') AND l.due_date IS NOT NULL ORDER BY l.id")]
    rnd.shuffle(open_leads)
    days = list(range(-3, 22)) + [0, 0, 1]
    for i, lid in enumerate(open_leads):
        day = days[i % len(days)]
        owner = managers[(i + i // len(days)) % len(managers)]
        db.execute("UPDATE leads SET due_date = ?, owner_id = ? WHERE id = ?",
                   ((today + timedelta(days=day)).isoformat(), owner, lid))


def add_followups(db, lead_id, day, count, managers, final=None):
    done = day + timedelta(days=1)
    for k in range(count):
        last = k == count - 1
        result = final if last and final else rnd.choice(["no_answer", "talking", "meeting_set"])
        db.execute("INSERT INTO followups (lead_id, channel, done_on, result, note, user_id) VALUES (?, ?, ?, ?, ?, ?)",
                   (lead_id, rnd.choice(["email", "phone", "in_person", "linkedin"]), done.isoformat(), result, None,
                    rnd.choice(managers)))
        done += timedelta(days=rnd.randint(3, 12))


if __name__ == "__main__":
    app = create_app()
    path = app.config["DATABASE"]
    if os.path.exists(path) and "--yes" not in sys.argv:
        if input(f"Базу {path} буде створено заново, усі дані зникнуть. Продовжити? (так/ні) ").strip().lower() not in ("так", "y", "yes"):
            sys.exit("Скасовано.")
    if os.path.exists(path):
        os.remove(path)
    with app.app_context():
        init_db()
        seed()
    with open(os.path.join(app.instance_path, "demo.json"), "w", encoding="utf-8") as f:
        json.dump({"logins": DEMO_LOGINS, "password": PASSWORD}, f, ensure_ascii=False)
    print("Демонстраційні дані створено. Логіни:", ", ".join(u for u, _ in DEMO_LOGINS), "· пароль:", PASSWORD)
