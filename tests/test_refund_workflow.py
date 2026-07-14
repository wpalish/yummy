"""Customer refund request ownership and MFA-admin resolution."""
from __future__ import annotations

import pytest

import app.accounts as A
from app.accounts import Accounts
from app.db import Store
from app.seed import seed


@pytest.fixture
def client(tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    import app.main as main_mod
    from fastapi.testclient import TestClient

    accounts = Accounts(tmp_path / "accounts.db")
    store = Store(tmp_path / "store.db")
    seed(store)
    monkeypatch.setattr(A, "accounts", accounts)
    monkeypatch.setattr(main_mod, "store", store)
    A._auth_hits.clear()
    A._jail.clear()
    main_mod._rate_hits.clear()
    main_mod._ai_hits.clear()

    admin_id = accounts.create("admin@example.com", A.hash_password("Secret123"), "admin")
    accounts.configure_mfa(admin_id, "admin@example.com")
    row = accounts.by_id(admin_id)
    admin_token = A.create_token(admin_id, "admin", ver=row["token_ver"], mfa_verified=True)
    return TestClient(main_mod.app), store, {"Authorization": f"Bearer {admin_token}"}


def register_customer(c, email):
    body = c.post("/auth/register", json={
        "email": email, "password": "Secret123", "accepted_terms": True,
    }).json()
    return {"Authorization": f"Bearer {body['access_token']}"}


def create_order(c, headers):
    box = c.get("/boxes").json()[0]
    response = c.post("/orders", headers=headers, json={
        "box_id": box["id"], "user_name": "Айша", "user_phone": "+77001234567",
    })
    assert response.status_code == 201
    return response.json()["order"], box


def test_only_owner_can_open_one_refund_request(client):
    c, _, _ = client
    owner = register_customer(c, "owner@example.com")
    other = register_customer(c, "other@example.com")
    order, _ = create_order(c, owner)
    payload = {"reason": "not_issued", "details": "Заведение не выдало заказ"}

    assert c.post(f"/me/orders/{order['id']}/refund-requests",
                  headers=other, json=payload).status_code == 409
    created = c.post(f"/me/orders/{order['id']}/refund-requests",
                     headers=owner, json=payload)
    assert created.status_code == 201 and created.json()["status"] == "pending"
    assert c.post(f"/me/orders/{order['id']}/refund-requests",
                  headers=owner, json=payload).status_code == 409
    mine = c.get("/me/refund-requests", headers=owner).json()
    assert len(mine) == 1 and mine[0]["order_id"] == order["id"]


def test_mfa_admin_resolves_refund_atomically_and_restores_inventory(client):
    c, store, admin = client
    owner = register_customer(c, "buyer@example.com")
    order, box = create_order(c, owner)
    before = store.box(box["id"]).qty_left
    request = c.post(
        f"/me/orders/{order['id']}/refund-requests", headers=owner,
        json={"reason": "venue_closed", "details": "На месте всё было закрыто"},
    ).json()

    reviewing = c.post(
        f"/admin/refund-requests/{request['id']}/decision", headers=admin,
        json={"action": "reviewing", "resolution": "Проверяем у партнёра"},
    )
    assert reviewing.status_code == 200 and reviewing.json()["status"] == "reviewing"
    approved = c.post(
        f"/admin/refund-requests/{request['id']}/decision", headers=admin,
        json={"action": "approve", "resolution": "Закрытие подтверждено"},
    )
    assert approved.status_code == 200 and approved.json()["status"] == "refunded"
    assert store.order_by_id(order["id"]).status == "refunded"
    assert store.box(box["id"]).qty_left == before + 1
    assert c.post(
        f"/admin/refund-requests/{request['id']}/decision", headers=admin,
        json={"action": "approve", "resolution": "Повтор"},
    ).status_code == 409


def test_issued_order_cannot_use_not_issued_refund_flow(client):
    c, _, admin = client
    owner = register_customer(c, "issued@example.com")
    order, _ = create_order(c, owner)
    assert c.post("/redeem", headers=admin, json={"code": order["code"]}).json()["ok"]
    response = c.post(
        f"/me/orders/{order['id']}/refund-requests", headers=owner,
        json={"reason": "not_issued", "details": "Пытаюсь вернуть выданный заказ"},
    )
    assert response.status_code == 409
