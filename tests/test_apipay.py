"""ApiPay.kz — реальная Kaspi-оплата: клиент, подпись вебхука, флоу заказа."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import apipay
from app import main as main_mod
from app.db import Store
from app.models import BoxCreate, Partner


def _iso(h: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()


class _Resp:
    def __init__(self, status, data):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data


# --------------------------------------------------------------------------- #
#  Нормализация телефона под формат ApiPay (8XXXXXXXXXX)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw,exp", [
    ("+7 701 234 56 78", "87012345678"),
    ("87012345678", "87012345678"),
    ("7012345678", "87012345678"),
    ("8 (701) 234-56-78", "87012345678"),
    ("123", None),
    ("", None),
])
def test_normalize_phone(raw, exp):
    assert apipay.normalize_phone(raw) == exp


# --------------------------------------------------------------------------- #
#  Подпись вебхука (HMAC-SHA256 сырого тела)
# --------------------------------------------------------------------------- #
def test_verify_webhook(monkeypatch):
    monkeypatch.setenv("APIPAY_WEBHOOK_SECRET", "s3cr3t")
    body = b'{"event":"invoice.status_changed"}'
    good = "sha256=" + hmac.new(b"s3cr3t", body, hashlib.sha256).hexdigest()
    assert apipay.verify_webhook(body, good) is True
    assert apipay.verify_webhook(body, "sha256=deadbeef") is False
    assert apipay.verify_webhook(body, "") is False
    # чужой секрет → невалидно
    bad = "sha256=" + hmac.new(b"other", body, hashlib.sha256).hexdigest()
    assert apipay.verify_webhook(body, bad) is False


def test_verify_webhook_no_secret(monkeypatch):
    monkeypatch.delenv("APIPAY_WEBHOOK_SECRET", raising=False)
    assert apipay.verify_webhook(b"x", "sha256=abc") is False   # нет секрета → не доверяем


# --------------------------------------------------------------------------- #
#  Клиент: создание инвойса, идемпотентность, деградация без ключа
# --------------------------------------------------------------------------- #
def test_create_invoice_success(monkeypatch):
    monkeypatch.setenv("APIPAY_API_KEY", "k")
    captured = {}

    def fake_post(url, json, headers, timeout):
        captured["url"] = url
        captured["body"] = json
        return _Resp(201, {"id": 42, "status": "processing"})

    monkeypatch.setattr(apipay.httpx, "post", fake_post)
    r = apipay.create_invoice("+77012345678", 990, "Yummy заказ", "ord_1")
    assert r["id"] == 42
    assert captured["body"]["phone_number"] == "87012345678"
    assert captured["body"]["amount"] == 990.0
    assert captured["body"]["external_order_id_idempotency"] == "ord_1"


def test_create_invoice_idempotent_409(monkeypatch):
    monkeypatch.setenv("APIPAY_API_KEY", "k")
    monkeypatch.setattr(apipay.httpx, "post",
                        lambda *a, **k: _Resp(409, {"id": 7, "status": "processing"}))
    assert apipay.create_invoice("87012345678", 500, "x", "dup")["id"] == 7


def test_create_invoice_error_raises(monkeypatch):
    monkeypatch.setenv("APIPAY_API_KEY", "k")
    monkeypatch.setattr(apipay.httpx, "post",
                        lambda *a, **k: _Resp(400, {"message": "bad", "error_code": "x"}))
    with pytest.raises(apipay.PaymentUnavailable):
        apipay.create_invoice("87012345678", 500, "x", "e")


def test_no_key_is_unavailable(monkeypatch):
    monkeypatch.delenv("APIPAY_API_KEY", raising=False)
    assert apipay.is_configured() is False
    with pytest.raises(apipay.PaymentUnavailable):
        apipay.create_invoice("87012345678", 500, "x", "e")


# --------------------------------------------------------------------------- #
#  Флоу заказа + вебхук end-to-end
# --------------------------------------------------------------------------- #
@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(main_mod, "_PAYMENT_MODE", "apipay")
    monkeypatch.setattr(main_mod, "_DEMO_PAY", False)
    monkeypatch.setenv("APIPAY_API_KEY", "k")
    monkeypatch.setenv("APIPAY_WEBHOOK_SECRET", "whsec")
    store = Store(path=tmp_path / "s.db")
    store.upsert_partner(Partner(id="p1", name="Кофейня А", district="Есильский р-н",
                                 address="ул. А"))
    # активный мерчант-аккаунт — без него платный бокс не продать
    store.upsert_payment_account("pa1", "p1", "pub1", "KZ-1", "kaspi")
    store.set_payment_account_status("p1", "active", payments_enabled=True)
    store.set_commission_rate("cr1", "p1", 1000)
    monkeypatch.setattr(main_mod, "store", store)
    main_mod._rate_hits.clear()
    box = store.create_box("b1", BoxCreate(
        partner_id="p1", category="bakery", title="Бокс", price=990, value_est=2600,
        qty=3, pickup_from=_iso(1), pickup_to=_iso(4)))
    return TestClient(main_mod.app), store, box


def test_order_creates_invoice_and_stays_pending(env, monkeypatch):
    c, store, box = env
    monkeypatch.setattr(apipay.httpx, "post",
                        lambda *a, **k: _Resp(201, {"id": 555, "status": "processing"}))
    r = c.post("/orders", json={"box_id": box.id, "user_name": "Али",
                                "user_phone": "+77010000000"})
    assert r.status_code == 201
    body = r.json()
    assert body["order"]["payment_status"] == "pending"
    assert body["qr_svg"] == ""                       # QR не выдаём до оплаты
    # инвойс привязан к заказу
    with store._conn() as conn:
        inv = conn.execute("SELECT invoice_id FROM orders WHERE id=?",
                           (body["order"]["id"],)).fetchone()[0]
    assert inv == "555"


def test_webhook_paid_confirms_order_and_accrues(env, monkeypatch):
    c, store, box = env
    monkeypatch.setattr(apipay.httpx, "post",
                        lambda *a, **k: _Resp(201, {"id": 777, "status": "processing"}))
    oid = c.post("/orders", json={"box_id": box.id, "user_name": "Али",
                                  "user_phone": "+77010000000"}).json()["order"]["id"]

    def _hook(status="paid"):
        payload = json.dumps({"event": "invoice.status_changed",
                              "invoice": {"id": 777, "status": status}}).encode()
        sig = "sha256=" + hmac.new(b"whsec", payload, hashlib.sha256).hexdigest()
        return c.post("/webhooks/apipay", content=payload,
                      headers={"X-Webhook-Signature": sig, "Content-Type": "application/json"})

    # неверная подпись → 401, заказ не оплачен
    bad = c.post("/webhooks/apipay", content=b"{}",
                 headers={"X-Webhook-Signature": "sha256=bad"})
    assert bad.status_code == 401

    assert _hook().status_code == 200
    with store._conn() as conn:
        assert conn.execute("SELECT payment_status FROM orders WHERE id=?",
                            (oid,)).fetchone()[0] == "paid"
    # комиссия начислена (10% от 990 = 9900 тиын)
    assert store.commission_summary("p1")["owed_minor"] == 9900
    # повторный вебхук идемпотентен: оплата не задваивается
    assert _hook().status_code == 200
    assert store.commission_summary("p1")["owed_minor"] == 9900
