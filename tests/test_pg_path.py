"""PG-путь: тесты гоняются на SQLite, прод — на Postgres. Этот файл закрывает
дыру «расхождение поймает только прод»: при заданном YUMMY_TEST_DATABASE_URL
(отдельная тестовая база Supabase/PG, НЕ прод!) схема и базовый CRUD прогоняются
на настоящем Postgres. Без переменной — skip, обычный прогон не замедляется.

Запуск:  YUMMY_TEST_DATABASE_URL=postgresql://... .venv/bin/python -m pytest tests/test_pg_path.py
"""
from __future__ import annotations

import importlib
import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.getenv("YUMMY_TEST_DATABASE_URL"),
    reason="YUMMY_TEST_DATABASE_URL не задан — PG-путь пропущен (см. docstring)",
)


@pytest.fixture
def pg_modules(monkeypatch):
    """Перезагрузить слой БД с DATABASE_URL тестового Postgres."""
    monkeypatch.setenv("DATABASE_URL", os.environ["YUMMY_TEST_DATABASE_URL"])
    import app.database as database_mod
    importlib.reload(database_mod)
    import app.db as db_mod
    importlib.reload(db_mod)
    import app.accounts as accounts_mod
    importlib.reload(accounts_mod)
    yield db_mod, accounts_mod
    # вернуть SQLite-режим для остальных тестов
    monkeypatch.delenv("DATABASE_URL")
    importlib.reload(database_mod)
    importlib.reload(db_mod)
    importlib.reload(accounts_mod)


def test_schema_and_crud_on_postgres(pg_modules):
    """Схема создаётся (включая миграции ADD COLUMN IF NOT EXISTS), CRUD живой."""
    db_mod, accounts_mod = pg_modules
    from app.models import BoxCreate, Partner

    store = db_mod.Store()                      # схема на PG
    pid = "pgtest_" + uuid.uuid4().hex[:8]
    store.upsert_partner(Partner(id=pid, name="PG Тест", district="Тест",
                                 address="ул. PG"))
    assert store.partner(pid) is not None

    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    b = store.create_box("b_" + pid, BoxCreate(
        partner_id=pid, category="bakery", title="PG бокс", price=990,
        value_est=2600, qty=2, pickup_from=(now + timedelta(hours=1)).isoformat(),
        pickup_to=(now + timedelta(hours=4)).isoformat()))
    o = store.create_order("o_" + pid, "YM-PG1", b, "Тест", "+7700",
                           user_id=None, require_payment=False)
    assert o and store.box(b.id).qty_left == 1
    assert len(store.partner_orders(pid, limit=10)) == 1
    assert store.partner_daily_stats(pid)       # substr/date работают и на PG

    users = accounts_mod.Accounts()
    email = f"pg-{uuid.uuid4().hex[:8]}@test.kz"
    uid = users.create(email, accounts_mod.hash_password("Pass1234"), "customer",
                       None, None)
    assert users.by_id(uid)["email"] == email
    users.jail_fail(email, 5, 600)              # auth_jail UPSERT — PG-диалект
    assert users.jail_get(email)["fails"] == 1
    users.jail_reset(email)
