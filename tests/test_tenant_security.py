"""Object-level authorization (BOLA/IDOR), PII и временные инварианты API."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from app.accounts import Accounts
from app.db import Store
from app.seed import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    import app.accounts as accounts_mod
    import app.main as main_mod
    from fastapi.testclient import TestClient

    accounts = Accounts(path=tmp_path / "accounts.db")
    store = Store(path=tmp_path / "store.db")
    seed(store)
    monkeypatch.setattr(accounts_mod, "accounts", accounts)
    monkeypatch.setattr(main_mod, "store", store)
    accounts_mod._auth_hits.clear()
    accounts_mod._jail.clear()
    main_mod._rate_hits.clear()
    main_mod._ai_hits.clear()
    return TestClient(main_mod.app), store


def register_partner(client, email: str):
    response = client.post("/auth/register", json={
        "email": email,
        "password": "Secret123",
        "role": "partner",
        "brand_name": email.split("@")[0],
        "address": "ул. Тестовая, 1",
        "district": "Нура р-н",
        "accepted_terms": True,
    })
    assert response.status_code == 201, response.text
    body = response.json()
    import app.accounts as accounts_mod
    accounts_mod.accounts.mark_email_verified(body["user"]["id"])
    accounts_mod.accounts.set_partner_status(body["user"]["id"], "approved")
    return body["user"], {"Authorization": f"Bearer {body['access_token']}"}


def create_owned_box(client, user: dict, headers: dict):
    now = datetime.now(timezone.utc)
    response = client.post("/boxes", headers=headers, json={
        "partner_id": user["partner_id"],
        "category": "bakery",
        "title": "Tenant box",
        "price": 900,
        "value_est": 2200,
        "qty": 3,
        "pickup_from": now.isoformat(),
        "pickup_to": (now + timedelta(hours=2)).isoformat(),
        "description": "Свежая выпечка",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_partner_private_orders_require_auth(client):
    c, _ = client
    user, headers = register_partner(c, "owner@yummy.kz")
    assert c.get("/partner/me", headers=headers).status_code == 200

    assert c.get("/partner/me/orders").status_code == 401
    assert c.get(f"/partners/{user['partner_id']}/orders").status_code == 401


def test_partner_cannot_cross_tenant_create_read_or_redeem(client):
    c, _ = client
    owner, owner_headers = register_partner(c, "owner@yummy.kz")
    intruder, intruder_headers = register_partner(c, "intruder@yummy.kz")
    c.get("/partner/me", headers=owner_headers)
    c.get("/partner/me", headers=intruder_headers)

    # Payload tenant id is untrusted; a partner cannot publish for another cafe.
    now = datetime.now(timezone.utc)
    forged = c.post("/boxes", headers=intruder_headers, json={
        "partner_id": owner["partner_id"], "category": "sweet", "title": "forged",
        "price": 500, "value_est": 1000, "qty": 1,
        "pickup_from": now.isoformat(),
        "pickup_to": (now + timedelta(hours=1)).isoformat(),
    })
    assert forged.status_code == 403

    box = create_owned_box(c, owner, owner_headers)
    order = c.post("/orders", json={
        "box_id": box["id"], "user_name": "Айша", "user_phone": "+77001234567",
    }).json()["order"]

    assert c.get(f"/partners/{owner['partner_id']}/orders",
                 headers=intruder_headers).status_code == 403
    assert c.get("/partner/me/orders", headers=intruder_headers).json() == []

    denied = c.post("/redeem", headers=intruder_headers, json={"code": order["code"]})
    assert denied.status_code == 200
    assert denied.json() == {
        "ok": False, "message": "Заказ с таким кодом не найден", "order": None,
    }
    issued = c.post("/redeem", headers=owner_headers, json={"code": order["code"]})
    assert issued.json()["ok"] is True


def test_public_order_status_is_redacted_and_code_has_high_entropy(client):
    c, _ = client
    owner, headers = register_partner(c, "codes@yummy.kz")
    box = create_owned_box(c, owner, headers)
    order = c.post("/orders", json={
        "box_id": box["id"], "user_name": "Секретное Имя",
        "user_phone": "+77007654321",
    }).json()["order"]

    assert re.fullmatch(r"YM-[2-9A-HJ-NP-Z]{5}-[2-9A-HJ-NP-Z]{5}", order["code"])
    public = c.get(f"/orders/{order['code']}")
    assert public.status_code == 200
    body = public.json()
    assert body["status"] == "paid"
    for secret in ("id", "box_id", "partner_id", "user_name", "user_phone"):
        assert secret not in body


def test_expired_box_is_hidden_and_cannot_be_ordered(client):
    c, store = client
    box = c.get("/boxes").json()[0]
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    with store._conn() as conn:
        conn.execute("UPDATE boxes SET pickup_to=? WHERE id=?", (past, box["id"]))

    assert box["id"] not in {item["id"] for item in c.get("/boxes").json()}
    response = c.post("/orders", json={
        "box_id": box["id"], "user_name": "Айша", "user_phone": "+77001234567",
    })
    assert response.status_code == 409
    assert "завершилось" in response.json()["detail"]


def test_order_code_generator_is_collision_resistant():
    from app.main import _order_code

    codes = {_order_code() for _ in range(10_000)}
    assert len(codes) == 10_000
    assert all(re.fullmatch(r"YM-[2-9A-HJ-NP-Z]{5}-[2-9A-HJ-NP-Z]{5}", c) for c in codes)
