"""Демо-данные: кофейни/пекарни Астаны + вечерние боксы.

Окна самовывоза задаются относительно текущего времени, чтобы демо всегда было
«в окне» (боксы можно забрать), когда бы ни запустили.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from .db import Store
from .models import BoxCreate, Partner

PARTNERS = [
    Partner(id="p1", name="Coffee Point", district="Левый берег", address="пр. Мангилик Ел, 55", rating=4.8),
    Partner(id="p2", name="Bake House", district="Левый берег", address="ул. Достык, 12", rating=4.7),
    Partner(id="p3", name="Donut Lab", district="Левый берег", address="ТРЦ Mega Silk Way", rating=4.6),
    Partner(id="p4", name="Сдоба", district="Алматинский р-н", address="ул. Кенесары, 40", rating=4.5),
    Partner(id="p5", name="Sweet Corner", district="Есильский р-н", address="пр. Кабанбай батыра, 7", rating=4.9),
    Partner(id="p6", name="Утром Кофе", district="Есильский р-н", address="ул. Сауран, 3", rating=4.6),
]

# (partner_id, category, title, price, value_est, qty, описание)
_BOXES = [
    ("p1", "sweet", "Вечерний Sweet Box", 990, 2600, 5, "Пончики, маффины, печенье — что осталось к вечеру."),
    ("p1", "snack", "Snack Box", 1190, 2900, 3, "Сэндвич + выпечка дня."),
    ("p2", "bakery", "Bakery Box", 890, 2400, 6, "Круассаны и булочки из утренней партии."),
    ("p3", "sweet", "Donut Box", 790, 2200, 8, "6 пончиков ассорти."),
    ("p4", "mixed", "Mixed Box", 1090, 2800, 4, "Сладкое + несладкое, сюрприз."),
    ("p5", "sweet", "Dessert Box", 1290, 3200, 3, "Пирожные и десерты дня."),
    ("p6", "bakery", "Утренняя выпечка", 850, 2300, 5, "Свежая выпечка по вечерней цене."),
]


def _partner_token(pid: str) -> str:
    """Токен кабинета партнёра: в проде задаётся через PARTNER_TOKEN_<ID>."""
    return os.environ.get(f"PARTNER_TOKEN_{pid.upper()}", f"pt-{pid}-demo")


def seed(store: Store) -> None:
    store.reset()
    for p in PARTNERS:
        store.upsert_partner(p, token=_partner_token(p.id))

    now = datetime.now(timezone.utc)
    pickup_from = (now - timedelta(minutes=30)).isoformat()
    pickup_to = (now + timedelta(hours=4)).isoformat()

    for i, (pid, cat, title, price, value, qty, desc) in enumerate(_BOXES, start=1):
        store.create_box(
            f"b{i}",
            BoxCreate(
                partner_id=pid, category=cat, title=title, price=price,
                value_est=value, qty=qty, pickup_from=pickup_from,
                pickup_to=pickup_to, description=desc,
            ),
        )
