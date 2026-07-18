"""Кабинеты партнёра и админа: CRUD боксов, владение, блокировка, CSV.

Главное здесь — ВЛАДЕНИЕ: раньше проверялась только роль, поэтому партнёр мог
править боксы чужого заведения и публиковать от его имени.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.accounts import Accounts, create_token
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
    for pid, name in (("p1", "Кофейня А"), ("p2", "Кофейня Б")):
        store.upsert_partner(Partner(id=pid, name=name, district="Есильский р-н",
                                     address=f"ул. {name}"))
    monkeypatch.setattr(main_mod, "store", store)
    accounts_mod._auth_hits.clear()
    accounts_mod._jail.clear()
    main_mod._rate_hits.clear()
    return TestClient(main_mod.app), store, users


def _staff(users, email: str, partner_id: str, partner_role: str = "owner") -> dict:
    """Создать сотрудника заведения и вернуть заголовок с его токеном."""
    uid = users.create(email, "x", "partner", None, None,
                       partner_id=partner_id, partner_role=partner_role)
    return {"Authorization": f"Bearer {create_token(uid, 'partner')}"}


def _admin(users, email: str = "boss@yummy.kz") -> dict:
    uid = users.create(email, "x", "admin", None, None)
    return {"Authorization": f"Bearer {create_token(uid, 'admin')}"}


def _box(store, pid: str = "p1") -> str:
    return store.create_box("b_" + pid, BoxCreate(
        partner_id=pid, category="bakery", title="Бокс", price=990, value_est=2600,
        qty=5, pickup_from=_iso(1), pickup_to=_iso(4))).id


# --------------------------------------------------------------------------- #
#  Владение: чужое трогать нельзя
# --------------------------------------------------------------------------- #
def test_partner_cannot_edit_foreign_box(env):
    c, store, users = env
    foreign = _box(store, "p2")
    h = _staff(users, "a@x.kz", "p1")
    assert c.patch(f"/boxes/{foreign}", json={"price": 500}, headers=h).status_code == 403
    assert c.delete(f"/boxes/{foreign}", headers=h).status_code == 403


def test_partner_cannot_publish_as_foreign(env):
    c, store, users = env
    h = _staff(users, "a@x.kz", "p1")
    r = c.post("/boxes", headers=h, json={
        "partner_id": "p2", "category": "bakery", "title": "Чужой", "price": 990,
        "value_est": 2600, "qty": 1, "pickup_from": _iso(1), "pickup_to": _iso(4)})
    assert r.status_code == 403


def test_partner_edits_own_box(env):
    c, store, users = env
    bid = _box(store, "p1")
    h = _staff(users, "a@x.kz", "p1")
    r = c.patch(f"/boxes/{bid}", json={"price": 790, "title": "Новый"}, headers=h)
    assert r.status_code == 200
    assert r.json()["price"] == 790 and r.json()["title"] == "Новый"


def test_admin_edits_any_box(env):
    c, store, users = env
    bid = _box(store, "p2")
    r = c.patch(f"/boxes/{bid}", json={"price": 500}, headers=_admin(users))
    assert r.status_code == 200


# --------------------------------------------------------------------------- #
#  Роли персонала: кассир не меняет витрину
# --------------------------------------------------------------------------- #
def test_cashier_cannot_edit(env):
    c, store, users = env
    bid = _box(store, "p1")
    h = _staff(users, "kassa@x.kz", "p1", "cashier")
    assert c.patch(f"/boxes/{bid}", json={"price": 500}, headers=h).status_code == 403
    assert c.delete(f"/boxes/{bid}", headers=h).status_code == 403


def test_manager_can_edit(env):
    c, store, users = env
    bid = _box(store, "p1")
    h = _staff(users, "man@x.kz", "p1", "manager")
    assert c.patch(f"/boxes/{bid}", json={"price": 800}, headers=h).status_code == 200


# --------------------------------------------------------------------------- #
#  Правка остатка и снятие с продажи
# --------------------------------------------------------------------------- #
def test_qty_change_keeps_booked(env):
    """Уменьшение остатка не «отбирает» уже забронированные боксы."""
    c, store, users = env
    bid = _box(store, "p1")                       # qty_total=5, qty_left=5
    store.create_order("o1", "YM-1", store.box(bid), "Али", "+7701", user_id=None,
                       require_payment=False)      # забронирован 1 → qty_left=4
    h = _staff(users, "a@x.kz", "p1")
    r = c.patch(f"/boxes/{bid}", json={"qty_total": 2}, headers=h)
    assert r.status_code == 200
    assert r.json()["qty_total"] == 2 and r.json()["qty_left"] == 1   # 2-1 бронь


def test_close_box_removes_from_catalog(env):
    c, store, users = env
    bid = _box(store, "p1")
    h = _staff(users, "a@x.kz", "p1")
    assert c.delete(f"/boxes/{bid}", headers=h).status_code == 200
    assert all(b.id != bid for b in store.boxes_available())
    assert c.delete(f"/boxes/{bid}", headers=h).status_code == 409   # повторно нельзя


def test_price_above_value_rejected(env):
    c, store, users = env
    bid = _box(store, "p1")
    h = _staff(users, "a@x.kz", "p1")
    assert c.patch(f"/boxes/{bid}", json={"price": 9999}, headers=h).status_code == 400


# --------------------------------------------------------------------------- #
#  Админ: блокировка и отзыв сессий
# --------------------------------------------------------------------------- #
def test_block_kills_sessions(env):
    c, store, users = env
    victim = users.create("v@x.kz", "x", "customer", None, None)
    vh = {"Authorization": f"Bearer {create_token(victim, 'customer')}"}
    assert c.get("/auth/me", headers=vh).status_code == 200
    assert c.post(f"/admin/users/{victim}/block", headers=_admin(users)).status_code == 200
    assert c.get("/auth/me", headers=vh).status_code in (401, 403)   # токен мёртв


def test_unblock_restores_access(env):
    """После разблокировки новый вход снова работает (старые токены мертвы)."""
    c, store, users = env
    ah = _admin(users)
    victim = users.create("v@x.kz", "x", "customer", None, None)
    c.post(f"/admin/users/{victim}/block", headers=ah)
    assert c.post(f"/admin/users/{victim}/block?active=true", headers=ah).status_code == 200
    ver = users.by_id(victim)["token_ver"]          # актуальная версия после блокировки
    fresh = {"Authorization": f"Bearer {create_token(victim, 'customer', ver=ver)}"}
    assert c.get("/auth/me", headers=fresh).status_code == 200


def test_admin_cannot_block_self(env):
    c, store, users = env
    uid = users.create("boss@yummy.kz", "x", "admin", None, None)
    h = {"Authorization": f"Bearer {create_token(uid, 'admin')}"}
    assert c.post(f"/admin/users/{uid}/block", headers=h).status_code == 409


def test_revoke_sessions(env):
    c, store, users = env
    victim = users.create("v@x.kz", "x", "customer", None, None)
    vh = {"Authorization": f"Bearer {create_token(victim, 'customer')}"}
    assert c.post(f"/admin/users/{victim}/revoke-sessions", headers=_admin(users)).status_code == 200
    assert c.get("/auth/me", headers=vh).status_code == 401       # разлогинен


def test_users_list_requires_admin(env):
    c, store, users = env
    h = _staff(users, "a@x.kz", "p1")
    assert c.get("/admin/users", headers=h).status_code == 403
    assert c.get("/admin/users", headers=_admin(users)).status_code == 200


# --------------------------------------------------------------------------- #
#  CSV
# --------------------------------------------------------------------------- #
def test_partner_csv_only_own(env):
    c, store, users = env
    h = _staff(users, "a@x.kz", "p1")
    assert c.get("/partners/p1/orders.csv", headers=h).status_code == 200
    assert c.get("/partners/p2/orders.csv", headers=h).status_code == 403


def test_csv_has_header_and_no_phone(env):
    c, store, users = env
    bid = _box(store, "p1")
    store.create_order("o1", "YM-9", store.box(bid), "Али", "+77010000000",
                       user_id=None, require_payment=False)
    body = c.get("/admin/orders.csv", headers=_admin(users)).text
    assert body.splitlines()[0].startswith("code,status")
    assert "+77010000000" not in body            # телефон не выгружаем
    assert "YM-9" in body


# --------------------------------------------------------------------------- #
#  Аналитика по дням
# --------------------------------------------------------------------------- #
def test_daily_stats_only_own_partner(env):
    c, store, users = env
    h = _staff(users, "a@x.kz", "p1")
    assert c.get("/partners/p1/daily-stats", headers=h).status_code == 200
    assert c.get("/partners/p2/daily-stats", headers=h).status_code == 403


def test_daily_stats_counts_revenue_and_losses(env):
    c, store, users = env
    bid = _box(store, "p1")                       # price=990, qty=5
    o1 = store.create_order("o1", "YM-1", store.box(bid), "Али", "+7701",
                            user_id=None, require_payment=False)
    o2 = store.create_order("o2", "YM-2", store.box(bid), "Даня", "+7702",
                            user_id=None, require_payment=False)
    store.redeem(o1.code)                    # o1 -> issued
    store.cancel_order(o2.code)              # o2 -> cancelled
    h = _staff(users, "a@x.kz", "p1")
    stats = c.get("/partners/p1/daily-stats", headers=h).json()
    assert len(stats) == 1
    today = stats[0]
    assert today["orders_count"] == 2
    assert today["revenue"] == 990                  # только issued, отменённый не считаем
    assert today["issued_count"] == 1
    assert today["lost_count"] == 1
