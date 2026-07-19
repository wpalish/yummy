"""Прод не должен вести себя как демо.

Целевое поведение (пункт 1 «убрать demo из production»):
  нет платёжного провайдера → покупка недоступна (а не фейковое «оплачено» + QR)
  нет verified merchant     → платный бокс нельзя опубликовать
  пустая БД                 → пустой каталог, а не выдуманные кофейни
"""
from __future__ import annotations

import importlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.db import Store
from app.models import BoxCreate, Partner


def _box(store: Store, pid: str = "p1") -> str:
    now = datetime.now(timezone.utc)
    b = store.create_box("b1", BoxCreate(
        partner_id=pid, category="bakery", title="Box", price=990, value_est=2600,
        qty=3, pickup_from=(now + timedelta(hours=1)).isoformat(),
        pickup_to=(now + timedelta(hours=4)).isoformat()))
    return b.id


def _app(monkeypatch, tmp_path, *, payment_mode: str):
    """Перезагружаем main с нужным режимом — флаги читаются на импорте."""
    monkeypatch.setenv("YUMMY_PAYMENT_MODE", payment_mode)
    import app.main as main_mod
    importlib.reload(main_mod)
    store = Store(path=tmp_path / "s.db")
    store.upsert_partner(Partner(id="p1", name="Real Cafe",
                                 district="Есильский р-н", address="ул. Абая, 1"))
    monkeypatch.setattr(main_mod, "store", store)
    main_mod._rate_hits.clear()
    return main_mod, store


# --------------------------------------------------------------------------- #
#  Покупка без платёжного провайдера
# --------------------------------------------------------------------------- #
def test_disabled_mode_blocks_purchase(monkeypatch, tmp_path):
    main_mod, store = _app(monkeypatch, tmp_path, payment_mode="disabled")
    bid = _box(store)
    c = TestClient(main_mod.app)
    r = c.post("/orders", json={"box_id": bid, "user_name": "Али", "user_phone": "+77010000000"})
    assert r.status_code == 503                      # покупка недоступна
    assert "недоступна" in r.json()["detail"].lower()
    assert store.count()[2] == 0                     # заказ НЕ создан


def test_demo_mode_still_sells(monkeypatch, tmp_path):
    """Пилот не сломан: в demo покупка работает как раньше."""
    main_mod, store = _app(monkeypatch, tmp_path, payment_mode="demo")
    bid = _box(store)
    c = TestClient(main_mod.app)
    r = c.post("/orders", json={"box_id": bid, "user_name": "Али", "user_phone": "+77010000000"})
    assert r.status_code == 201 and r.json()["order"]["code"]


def test_disabled_mode_allows_purchase_when_merchant_active(monkeypatch, tmp_path):
    """С активным мерчантом продажа доступна и в прод-режиме."""
    main_mod, store = _app(monkeypatch, tmp_path, payment_mode="disabled")
    store.upsert_payment_account("pa1", "p1", "pub1", "merchant-1", "kaspi")
    store.set_payment_account_status("p1", "active", payments_enabled=True)
    assert store.can_sell_paid("p1")
    bid = _box(store)
    c = TestClient(main_mod.app)
    r = c.post("/orders", json={"box_id": bid, "user_name": "Али", "user_phone": "+77010000000"})
    assert r.status_code == 201


# --------------------------------------------------------------------------- #
#  Публикация без verified merchant
# --------------------------------------------------------------------------- #
def test_disabled_mode_blocks_publishing_without_merchant(monkeypatch, tmp_path):
    main_mod, store = _app(monkeypatch, tmp_path, payment_mode="disabled")
    now = datetime.now(timezone.utc)
    c = TestClient(main_mod.app)
    r = c.post("/boxes", json={
        "partner_id": "p1", "category": "bakery", "title": "Box", "price": 990,
        "value_est": 2600, "qty": 3,
        "pickup_from": (now + timedelta(hours=1)).isoformat(),
        "pickup_to": (now + timedelta(hours=4)).isoformat()})
    assert r.status_code == 403


# --------------------------------------------------------------------------- #
#  Пустая БД → пустой каталог (без выдуманных кофеен)
# --------------------------------------------------------------------------- #
def test_no_demo_seed_in_prod(monkeypatch, tmp_path):
    monkeypatch.setenv("YUMMY_ENFORCE_AUTH", "1")
    monkeypatch.setenv("YUMMY_SECRET_KEY", "x" * 40)
    monkeypatch.delenv("YUMMY_DEMO_SEED", raising=False)
    import app.accounts as accounts_mod
    importlib.reload(accounts_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    assert main_mod._DEMO_SEED is False              # прод не сеет демо
    store = Store(path=tmp_path / "empty.db")
    monkeypatch.setattr(main_mod, "store", store)
    with TestClient(main_mod.app) as c:              # lifespan отработал
        assert c.get("/partners").json() == []       # пустой каталог, не 6 кофеен


def test_demo_seed_off_by_default(monkeypatch, tmp_path):
    """Fail-closed: без флага защита ВКЛЮЧЕНА → демо НЕ сеется.
    (Раньше было наоборот — забытый флаг превращал прод в демо.)"""
    monkeypatch.delenv("YUMMY_ENFORCE_AUTH", raising=False)
    monkeypatch.delenv("YUMMY_DEMO_SEED", raising=False)
    import app.accounts as accounts_mod
    importlib.reload(accounts_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    assert main_mod._DEMO_SEED is False


def test_demo_seed_on_explicit_optout(monkeypatch, tmp_path):
    """Локальное демо живо, но только при явном YUMMY_ENFORCE_AUTH=0."""
    monkeypatch.setenv("YUMMY_ENFORCE_AUTH", "0")
    monkeypatch.delenv("YUMMY_DEMO_SEED", raising=False)
    import app.accounts as accounts_mod
    importlib.reload(accounts_mod)
    import app.main as main_mod
    importlib.reload(main_mod)
    assert main_mod._DEMO_SEED is True
