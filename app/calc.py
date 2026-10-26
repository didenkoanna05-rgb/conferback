"""Розрахункові функції ConferBack.

Тут записано чотири формальні моделі з підрозділу 3.6.5. Функції не
звертаються до бази й вебінтерфейсу, тому їх легко перевірити тестами.
"""
from datetime import date, timedelta

# Формула (3.4): через скільки днів після розмови робити фолоу-ап
# залежно від рівня зацікавленості (3 — гарячий, 1 — холодний).
FOLLOWUP_DELAY_DAYS = {3: 0, 2: 2, 1: 14}

# Таблиця 3.8: верхня межа діапазону, висновок, колір позначки.
ROI_BANDS = [
    (1, "витрати не повернулися", "danger"),
    (3, "витрати повернулися, але результат нижчий за норму", "warning"),
    (5, "результат у межах норми", "success"),
    (float("inf"), "результат вищий за норму", "primary"),
]

# Формула (3.3): пороги як середній бал на один критерій.
SCORE_HIGH = 3.5
SCORE_LOW = 2.5


def followup_date(intent, captured_on=None):
    """Дата фолоу-апу за рівнем зацікавленості, формула (3.4), ФВ-12."""
    captured_on = captured_on or date.today()
    return captured_on + timedelta(days=FOLLOWUP_DELAY_DAYS[int(intent)])


def roi(revenue_new, revenue_accelerated, cost):
    """Коефіцієнт окупності, формула (3.1), ФВ-17.

    Повертає None, якщо витрат ще не внесено: ділити на нуль не можна,
    а нульова окупність ввела б в оману.
    """
    if not cost:
        return None
    return (revenue_new + revenue_accelerated) / cost


def roi_verdict(value):
    """Текстовий висновок і колір для коефіцієнта окупності (табл. 3.8)."""
    if value is None:
        return "витрати ще не внесено", "secondary"
    for limit, text, tone in ROI_BANDS:
        if value < limit:
            return text, tone
    return ROI_BANDS[-1][1], ROI_BANDS[-1][2]


def forecast(meetings, close_rate, avg_deal, cost):
    """Прогнозний результат до події, формула (3.2): P = K·Ch·V − C."""
    if close_rate is None or avg_deal is None:
        return None
    return meetings * close_rate * avg_deal - (cost or 0)


def score_verdict(total, n):
    """Рекомендація щодо участі за сумою балів S і кількістю критеріїв n, формула (3.3), ФВ-04."""
    if n <= 0:
        return None
    if total >= SCORE_HIGH * n:
        return {"code": "go", "text": "участь рекомендовано", "tone": "success"}
    if total >= SCORE_LOW * n:
        return {"code": "review", "text": "окремий розгляд", "tone": "warning"}
    return {"code": "no", "text": "участь не рекомендовано", "tone": "danger"}


def score_thresholds(n):
    """Пороги для n критеріїв: (верхній, нижній, максимум)."""
    return SCORE_HIGH * n, SCORE_LOW * n, 5 * n


def split_queue(leads, today=None):
    """Розподіл черги на прострочені, сьогоднішні та майбутні, ФВ-14."""
    today = (today or date.today()).isoformat()
    groups = {"overdue": [], "today": [], "upcoming": []}
    for lead in leads:
        due = lead["due_date"]
        if due < today:
            groups["overdue"].append(lead)
        elif due == today:
            groups["today"].append(lead)
        else:
            groups["upcoming"].append(lead)
    return groups


def is_qualified(icp_fit, status):
    """Кваліфікований лід: відповідність профілю не нижче 2 і не позначений як неперспективний."""
    return icp_fit is not None and icp_fit >= 2 and status != "no_action"
