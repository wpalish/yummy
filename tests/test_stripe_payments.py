"""Stripe Checkout reservation, reconciliation and webhook idempotency."""
from __future__ import annotations

import json

import pytest

from app.accounts import Accounts
from app.db import Store
from app.payments import PaymentUnavailable
from app.seed import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    import app.accounts as accounts_mod
    import app.main as main_mod
    from fastapi.testclient import TestClient

    accounts = Accounts(tmp_path / "accounts.db")
    store = Store(tmp_path / "store.db")
    seed(store)
    monkeypatch.setattr(accounts_mod, "accounts", accounts)
    monkeypatch.setattr(main_mod, "store", store)
    accounts_mod._auth_hits.clear()
    accounts_mod._jail.clear()
    main_mod._rate_hits.clear()
    main_mod._ai_hits.clear()
    return TestClient(main_mod.app), store, main_mod


def payload(box_id):
    return {"box_id": box_id, "user_name": "Айша", "user_phone": "+77001234567"}


def test_checkout_reserves_inventory_and_paid_webhook_reconciles(client, monkeypatch):
    c, store, main = client
    box = c.get("/boxes").json()[0]
    before = box["qty_left"]
    monkeypatch.setattr(main.payment_gateway, "create_checkout", lambda **kwargs: {
        "id": "cs_test_secure_123", "url": "https://checkout.stripe.com/c/pay/test"
    })
    created = c.post("/checkout/sessions", json=payload(box["id"]))
    assert created.status_code == 201
    assert created.json()["checkout_url"].startswith("https://checkout.stripe.com/")
    assert store.box(box["id"]).qty_left == before - 1
    pending = c.get("/checkout/sessions/cs_test_secure_123").json()
    assert pending["payment_status"] == "pending" and pending["qr_svg"] is None

    payment = store.checkout_status("cs_test_secure_123")[0]
    event = {
        "id": "evt_paid_1", "type": "checkout.session.completed",
        "data": {"object": {
            "metadata": {"payment_id": payment.id, "order_id": payment.order_id},
            "payment_status": "paid", "amount_total": payment.amount_minor,
            "currency": payment.currency, "client_reference_id": payment.order_id,
            "payment_intent": "pi_test_123",
        }},
    }
    monkeypatch.setattr(main.payment_gateway, "construct_event",
                        lambda raw, signature: event)
    webhook = c.post("/webhooks/stripe", content=json.dumps(event),
                     headers={"Content-Type": "application/json", "Stripe-Signature": "test"})
    assert webhook.status_code == 200 and webhook.json()["result"] == "paid"
    duplicate = c.post("/webhooks/stripe", content=json.dumps(event),
                       headers={"Content-Type": "application/json", "Stripe-Signature": "test"})
    assert duplicate.json()["result"] == "duplicate"
    paid = c.get("/checkout/sessions/cs_test_secure_123").json()
    assert paid["payment_status"] == "paid" and paid["qr_svg"]


def test_amount_mismatch_never_marks_order_paid(client, monkeypatch):
    c, store, main = client
    box = c.get("/boxes").json()[0]
    monkeypatch.setattr(main.payment_gateway, "create_checkout", lambda **kwargs: {
        "id": "cs_mismatch", "url": "https://checkout.stripe.com/test"
    })
    c.post("/checkout/sessions", json=payload(box["id"]))
    payment, order = store.checkout_status("cs_mismatch")
    event = {"id": "evt_bad", "type": "checkout.session.completed", "data": {"object": {
        "metadata": {"payment_id": payment.id}, "payment_status": "paid",
        "amount_total": 1, "currency": "kzt", "client_reference_id": order.id,
    }}}
    monkeypatch.setattr(main.payment_gateway, "construct_event", lambda raw, sig: event)
    response = c.post("/webhooks/stripe", content=json.dumps(event),
                      headers={"Content-Type": "application/json", "Stripe-Signature": "test"})
    assert response.json()["result"] == "rejected"
    assert store.order_by_id(order.id).status == "payment_pending"


def test_expired_reservation_releases_inventory_once(client, monkeypatch):
    c, store, main = client
    box = c.get("/boxes").json()[0]
    before = box["qty_left"]
    monkeypatch.setattr(main.payment_gateway, "create_checkout", lambda **kwargs: {
        "id": "cs_expire", "url": "https://checkout.stripe.com/test"
    })
    c.post("/checkout/sessions", json=payload(box["id"]))
    with store._conn() as connection:
        connection.execute("UPDATE payments SET reservation_expires_at='2000-01-01T00:00:00+00:00' WHERE checkout_session_id='cs_expire'")
    assert store.expire_payment_reservations() == 1
    assert store.expire_payment_reservations() == 0
    assert store.box(box["id"]).qty_left == before


def test_stripe_failure_releases_reservation(client, monkeypatch):
    c, store, main = client
    box = c.get("/boxes").json()[0]
    before = box["qty_left"]

    def fail(**kwargs):
        raise PaymentUnavailable("down")

    monkeypatch.setattr(main.payment_gateway, "create_checkout", fail)
    response = c.post("/checkout/sessions", json=payload(box["id"]))
    assert response.status_code == 503
    assert store.box(box["id"]).qty_left == before
