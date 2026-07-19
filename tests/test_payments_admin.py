"""Платёжные аккаунты и комиссии: шифрование реквизитов, suspension,
ротация, счета (commission_invoices), сторно при refund."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import credvault
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
    store.upsert_partner(Partner(id="p1", name="Кофейня А", district="Есильский р-н",
                                 address="ул. А"))
    monkeypatch.setattr(main_mod, "store", store)
    accounts_mod._auth_hits.clear()
    accounts_mod._jail.clear()
    main_mod._rate_hits.clear()
    uid = users.create("boss@yummy.kz", "x", "admin", None, None)
    admin = {"Authorization": f"Bearer {create_token(uid, 'admin')}"}
    return TestClient(main_mod.app), store, users, admin


def _paid_order(store, oid: str = "o1", code: str = "YM-1"):
    box = store.create_box("b_" + oid, BoxCreate(
        partner_id="p1", category="bakery", title="Бокс", price=1000, value_est=2600,
        qty=5, pickup_from=_iso(1), pickup_to=_iso(4)))
    return store.create_order(oid, code, box, "Али", "+7701", user_id=None,
                              require_payment=False)


# --------------------------------------------------------------------------- #
#  Шифрование merchant_reference
# --------------------------------------------------------------------------- #
def test_credvault_roundtrip_and_tamper():
    ct = credvault.encrypt("KZ-MERCHANT-0042")
    assert ct.startswith("enc1:") and "0042" not in ct
    assert credvault.decrypt(ct) == "KZ-MERCHANT-0042"
    with pytest.raises(ValueError):
        credvault.decrypt(ct[:-6] + "AAAAAA")       # порченный tag
    assert credvault.decrypt("легаси-плейнтекст") == "легаси-плейнтекст"


def test_merchant_reference_encrypted_at_rest(env):
    c, store, users, admin = env
    c.post("/partners/p1/payment-account", headers=admin,
           json={"merchant_reference": "KZ-SECRET-7777"})
    # в БД — только шифртекст
    with store._conn() as conn:
        raw = conn.execute("SELECT merchant_reference FROM partner_payment_accounts"
                           " WHERE partner_id='p1'").fetchone()[0]
    assert raw.startswith("enc1:") and "7777" not in raw
    # наружу — только маска
    body = c.get("/partners/p1/payment-account").json()
    assert body["merchant_masked"] == "…7777"
    assert "merchant_reference" not in body


def test_admin_list_shows_mask_only(env):
    c, store, users, admin = env
    c.post("/partners/p1/payment-account", headers=admin,
           json={"merchant_reference": "KZ-SECRET-1234"})
    rows = c.get("/admin/payment-accounts", headers=admin).json()
    assert len(rows) == 1
    r = rows[0]
    assert r["merchant_masked"] == "…1234" and r["encrypted"] is True
    assert "merchant_reference" not in r
    assert "owed_minor" in r                        # долг по комиссии приклеен


# --------------------------------------------------------------------------- #
#  Suspension и ротация
# --------------------------------------------------------------------------- #
def test_suspend_blocks_paid_boxes(env):
    c, store, users, admin = env
    c.post("/partners/p1/payment-account", headers=admin,
           json={"merchant_reference": "KZ-1"})
    c.post("/partners/p1/payment-account/activate", headers=admin)
    assert store.can_sell_paid("p1") is True
    r = c.post("/partners/p1/payment-account/suspend", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "suspended"
    assert store.can_sell_paid("p1") is False


def test_rotate_changes_public_id_and_reference(env):
    c, store, users, admin = env
    c.post("/partners/p1/payment-account", headers=admin,
           json={"merchant_reference": "KZ-OLD"})
    old_pub = store.payment_account("p1")["public_id"]
    r = c.post("/partners/p1/payment-account/rotate", headers=admin,
               json={"merchant_reference": "KZ-NEW-9999"})
    assert r.status_code == 200
    a = store.payment_account("p1")
    assert a["public_id"] != old_pub
    assert a["merchant_reference"] == "KZ-NEW-9999"
    assert r.json()["merchant_masked"] == "…9999"


def test_payment_admin_routes_require_admin(env):
    c, store, users, admin = env
    uid = users.create("p@x.kz", "x", "partner", None, None,
                       partner_id="p1", partner_role="owner")
    ph = {"Authorization": f"Bearer {create_token(uid, 'partner')}"}
    assert c.get("/admin/payment-accounts", headers=ph).status_code == 403
    assert c.post("/partners/p1/payment-account/suspend", headers=ph).status_code == 403
    assert c.post("/partners/p1/commission-invoice", headers=ph).status_code == 403


# --------------------------------------------------------------------------- #
#  Счета (commission_invoices) и сторно при refund
# --------------------------------------------------------------------------- #
def _setup_commission(c, store, admin):
    c.post("/partners/p1/payment-account", headers=admin,
           json={"merchant_reference": "KZ-1"})
    c.post("/partners/p1/payment-account/activate", headers=admin)
    c.post("/partners/p1/commission-rule", headers=admin, json={"rate_bps": 1000})


def test_invoice_aggregates_accrued(env):
    c, store, users, admin = env
    _setup_commission(c, store, admin)
    o1 = _paid_order(store, "o1", "YM-1"); store.accrue_commission("l1", o1)
    o2 = _paid_order(store, "o2", "YM-2"); store.accrue_commission("l2", o2)
    r = c.post("/partners/p1/commission-invoice", headers=admin)
    assert r.status_code == 201
    inv = r.json()
    # 2 заказа по 1000 тг, 10% = 100 тг каждый = 20000 тиын
    assert inv["total_minor"] == 20_000 and inv["entries_count"] == 2
    # повторный счёт — нечего выставлять
    assert c.post("/partners/p1/commission-invoice", headers=admin).status_code == 409


def test_refund_reverses_commission_before_invoice(env):
    c, store, users, admin = env
    _setup_commission(c, store, admin)
    o = _paid_order(store)
    store.accrue_commission("l1", o)
    assert store.commission_summary("p1")["owed_minor"] == 10_000
    assert c.post(f"/admin/refund/{o.id}", headers=admin).status_code == 200
    assert store.commission_entry(o.id)["status"] == "reversed"   # сторно
    assert store.commission_summary("p1")["owed_minor"] == 0
    # сторнированное в счёт не попадает
    assert c.post("/partners/p1/commission-invoice", headers=admin).status_code == 409


def test_invoice_paid_and_void(env):
    c, store, users, admin = env
    _setup_commission(c, store, admin)
    o = _paid_order(store)
    store.accrue_commission("l1", o)
    iid = c.post("/partners/p1/commission-invoice", headers=admin).json()["id"]
    # оплата
    r = c.post(f"/admin/commission-invoices/{iid}/paid", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "paid"
    # оплаченный второй раз не закрыть
    assert c.post(f"/admin/commission-invoices/{iid}/void", headers=admin).status_code == 404


def test_invoice_void_returns_entries_to_pool(env):
    c, store, users, admin = env
    _setup_commission(c, store, admin)
    o = _paid_order(store)
    store.accrue_commission("l1", o)
    iid = c.post("/partners/p1/commission-invoice", headers=admin).json()["id"]
    assert c.post(f"/admin/commission-invoices/{iid}/void",
                  headers=admin).json()["status"] == "void"
    # строки вернулись в пул → новый счёт выставляется
    r2 = c.post("/partners/p1/commission-invoice", headers=admin)
    assert r2.status_code == 201 and r2.json()["total_minor"] == 10_000
