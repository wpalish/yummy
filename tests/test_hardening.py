"""Харднинг №6–11: jail в БД, пагинация, сброс пароля, персистентный аудит."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.accounts import Accounts, create_token, hash_password
from app.db import Store
from app.models import BoxCreate, Partner


def _iso(h: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()


@pytest.fixture
def env(tmp_path, monkeypatch):
    import app.accounts as accounts_mod

    monkeypatch.setattr(accounts_mod, "_ENFORCE", True)
    users = Accounts(path=tmp_path / "u.db")
    monkeypatch.setattr(accounts_mod, "accounts", users)
    store = Store(path=tmp_path / "s.db")
    store.upsert_partner(Partner(id="p1", name="Кофейня", district="Есильский р-н",
                                 address="ул. А"))
    monkeypatch.setattr(main_mod, "store", store)
    accounts_mod._auth_hits.clear()
    main_mod._rate_hits.clear()
    return TestClient(main_mod.app), store, users


# --------------------------------------------------------------------------- #
#  №6: jail переживает «рестарт процесса»
# --------------------------------------------------------------------------- #
def test_jail_survives_restart(tmp_path):
    users = Accounts(path=tmp_path / "j.db")
    for _ in range(5):
        users.jail_fail("brute@x.kz", 5, 600)
    assert users.jail_get("brute@x.kz")["locked_until"] > 0
    # «рестарт»: новый инстанс над тем же файлом — блок на месте
    users2 = Accounts(path=tmp_path / "j.db")
    import time
    r = users2.jail_get("brute@x.kz")
    assert r and r["locked_until"] > time.time()
    users2.jail_reset("brute@x.kz")
    assert users2.jail_get("brute@x.kz") is None


# --------------------------------------------------------------------------- #
#  №7: пагинация
# --------------------------------------------------------------------------- #
def test_orders_pagination(env):
    c, store, users = env
    box = store.create_box("b1", BoxCreate(
        partner_id="p1", category="bakery", title="Бокс", price=990, value_est=2600,
        qty=30, pickup_from=_iso(1), pickup_to=_iso(4)))
    for i in range(25):
        store.create_order(f"o{i}", f"YM-{i}", box, "Али", "+7701",
                           user_id=None, require_payment=False)
    assert len(store.orders(limit=10)) == 10
    assert len(store.orders(limit=10, offset=20)) == 5
    assert len(store.partner_orders("p1", limit=7)) == 7
    uid = users.create("a@x.kz", "x", "admin", None, None)
    h = {"Authorization": f"Bearer {create_token(uid, 'admin')}"}
    assert len(c.get("/admin/orders?limit=10", headers=h).json()) == 10
    assert len(c.get("/admin/orders?limit=10&offset=20", headers=h).json()) == 5
    # CSV — полный, без пагинации (бухгалтерия)
    csv_body = c.get("/admin/orders.csv", headers=h).text
    assert csv_body.count("\n") >= 25


# --------------------------------------------------------------------------- #
#  №10: сброс пароля
# --------------------------------------------------------------------------- #
def test_reset_flow(env):
    c, store, users = env
    users.create("u@x.kz", hash_password("OldPass1"), "customer", None, None)
    raw = users.issue_reset_token("u@x.kz")
    assert raw
    r = c.post("/auth/reset-password", json={"token": raw, "password": "NewPass1"})
    assert r.status_code == 200
    # старый пароль мёртв, новый работает
    assert c.post("/auth/login", json={"email": "u@x.kz", "password": "OldPass1"}).status_code == 401
    assert c.post("/auth/login", json={"email": "u@x.kz", "password": "NewPass1"}).status_code == 200
    # токен одноразовый
    assert c.post("/auth/reset-password",
                  json={"token": raw, "password": "Xyz12345"}).status_code == 400


def test_reset_no_user_enumeration(env):
    c, store, users = env
    users.create("real@x.kz", hash_password("Pass1234"), "customer", None, None)
    a = c.post("/auth/request-reset", json={"email": "real@x.kz"})
    b = c.post("/auth/request-reset", json={"email": "ghost@x.kz"})
    assert a.status_code == b.status_code == 200
    assert a.json() == b.json()                 # ответы неотличимы


def test_reset_token_for_unknown_email_is_none(env):
    c, store, users = env
    assert users.issue_reset_token("nobody@x.kz") is None


# --------------------------------------------------------------------------- #
#  №11: аудит в БД, IP — хешем, retention
# --------------------------------------------------------------------------- #
def test_audit_persisted_with_hashed_ip(env):
    c, store, users = env
    users.create("u@x.kz", hash_password("Pass1234"), "customer", None, None)
    c.post("/auth/login", json={"email": "u@x.kz", "password": "WRONG!!1"})
    rows = users.audit_recent()
    assert any("login FAIL" in r["event"] for r in rows)
    joined = " ".join(r["event"] for r in rows)
    assert "testclient" not in joined           # сырой IP не пишется — только хеш


def test_audit_retention_sweep(env):
    c, store, users = env
    users.audit_write("старое событие")
    with users._conn() as conn:
        conn.execute("UPDATE audit_log SET ts=?",
                     ((datetime.now(timezone.utc) - timedelta(days=120)).isoformat(),))
    assert users.audit_sweep() >= 1
    assert not any("старое" in r["event"] for r in users.audit_recent())


def test_admin_audit_endpoint(env):
    c, store, users = env
    uid = users.create("boss@x.kz", "x", "admin", None, None)
    h = {"Authorization": f"Bearer {create_token(uid, 'admin')}"}
    users.audit_write("audit: тестовое событие")
    rows = c.get("/admin/audit", headers=h).json()
    assert any("тестовое" in r["event"] for r in rows)
    # не-админу нельзя
    pu = users.create("p@x.kz", "x", "partner", None, None,
                      partner_id="p1", partner_role="owner")
    ph = {"Authorization": f"Bearer {create_token(pu, 'partner')}"}
    assert c.get("/admin/audit", headers=ph).status_code == 403
