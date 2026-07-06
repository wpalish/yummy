"""Демо-данные: кофейни/пекарни Астаны + вечерние боксы.

Районы — реальные районы Астаны (без пересечений). Окна самовывоза у каждого
бокса свои (смещение от текущего времени), чтобы демо выглядело живым.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .db import Store
from .models import BoxCreate, Partner

PARTNERS = [
    Partner(id="p1", name="Coffee Point", district="Есильский р-н", address="пр. Мангилик Ел, 55", rating=4.8, lat=51.090, lng=71.416),
    Partner(id="p2", name="Bake House", district="Сарыарка р-н", address="ул. Бейбитшилик, 33", rating=4.7, lat=51.180, lng=71.408),
    Partner(id="p3", name="Donut Lab", district="Есильский р-н", address="ТРЦ Mega Silk Way", rating=4.6, lat=51.089, lng=71.402),
    Partner(id="p4", name="Сдоба", district="Алматинский р-н", address="ул. Кенесары, 40", rating=4.5, lat=51.165, lng=71.419),
    Partner(id="p5", name="Sweet Corner", district="Есильский р-н", address="пр. Кабанбай батыра, 7", rating=4.9, lat=51.132, lng=71.437),
    Partner(id="p6", name="Утром Кофе", district="Алматинский р-н", address="ул. Богенбай батыра, 23", rating=4.6, lat=51.166, lng=71.446),
]

# (partner_id, category, title, price, value_est, qty, старт_мин, длит_ч, описание)
_BOXES = [
    ("p1", "sweet", "Вечерний Sweet Box", 990, 2600, 5, -20, 4,
     "Обычно внутри: 2 пончика, маффин и печенье. Состав меняется день ко дню."),
    ("p1", "snack", "Snack Box", 1190, 2900, 3, 40, 3,
     "Обычно внутри: сэндвич, круассан и выпечка дня."),
    ("p2", "bakery", "Bakery Box", 890, 2400, 6, -10, 5,
     "Обычно внутри: 2 круассана, булочка с корицей, багет. Из утренней партии."),
    ("p3", "sweet", "Donut Box", 790, 2200, 8, 90, 4,
     "Обычно внутри: 6 пончиков ассорти (глазурь, шоколад, посыпка)."),
    ("p4", "mixed", "Mixed Box", 1090, 2800, 4, 0, 3,
     "Обычно внутри: сэндвич + 2 позиции сладкой выпечки. Сюрприз дня."),
    ("p5", "sweet", "Dessert Box", 1290, 3200, 3, 30, 2,
     "Обычно внутри: 2 пирожных и десерт дня (чизкейк или тирамису)."),
    ("p6", "bakery", "Утренняя выпечка", 850, 2300, 5, -30, 6,
     "Обычно внутри: 3–4 позиции свежей выпечки по вечерней цене."),
]


def seed(store: Store) -> None:
    store.reset()
    for p in PARTNERS:
        store.upsert_partner(p)

    def _round30(dt: datetime) -> datetime:
        """Окно выдачи с «человеческими» минутами (:00 / :30)."""
        return dt.replace(minute=0 if dt.minute < 30 else 30, second=0, microsecond=0)

    now = datetime.now(timezone.utc)
    for i, (pid, cat, title, price, value, qty, start_min, dur_h, desc) in enumerate(_BOXES, start=1):
        pickup_from = _round30(now + timedelta(minutes=start_min))
        pickup_to = pickup_from + timedelta(hours=dur_h)
        store.create_box(
            f"b{i}",
            BoxCreate(
                partner_id=pid, category=cat, title=title, price=price,
                value_est=value, qty=qty, pickup_from=pickup_from.isoformat(),
                pickup_to=pickup_to.isoformat(), description=desc,
            ),
        )
