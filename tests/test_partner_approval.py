"""Partner onboarding: pending-by-default, admin approval and suspension."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

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
    admin_row = accounts.by_id(admin_id)
    admin_token = A.create_token(
        admin_id, "admin", ver=int(admin_row["token_ver"]), mfa_verified=True,
    )
    return TestClient(main_mod.app), accounts, store, {
        "Authorization": f"Bearer {admin_token}"
    }


def register_partner(c):
    response = c.post("/auth/register", json={
        "email": "cafe@example.com", "password": "Secret123", "role": "partner",
        "brand_name": "Pending Cafe", "address": "ул. Тестовая, 1",
        "district": "Нура р-н", "accepted_terms": True,
    })
    assert response.status_code == 201
    body = response.json()
    return body["user"], {"Authorization": f"Bearer {body['access_token']}"}


def box_payload(partner_id):
    now = datetime.now(timezone.utc)
    return {
        "partner_id": partner_id, "category": "bakery", "title": "Approved box",
        "price": 900, "value_est": 2200, "qty": 2,
        "pickup_from": now.isoformat(),
        "pickup_to": (now + timedelta(hours=2)).isoformat(),
    }


def test_pending_partner_cannot_publish_read_orders_or_use_ai(client):
    c, _, _, _ = client
    user, headers = register_partner(c)
    assert user["partner_status"] == "pending"
    assert c.get("/partner/me", headers=headers).status_code == 200
    assert c.get("/partner/me/orders", headers=headers).status_code == 403
    assert c.post("/boxes", headers=headers,
                  json=box_payload(user["partner_id"])).status_code == 403
    assert c.post("/ai/describe-box", headers=headers,
                  json={"category": "bakery", "notes": "круассаны"}).status_code == 403
    assert user["partner_id"] not in {p["id"] for p in c.get("/partners").json()}


def test_admin_approval_materializes_tenant_and_enables_operations(client):
    c, _, _, admin_headers = client
    user, headers = register_partner(c)
    applications = c.get("/admin/partner-applications?status=pending",
                         headers=admin_headers)
    assert applications.status_code == 200
    assert applications.json()[0]["user_id"] == user["id"]

    blocked = c.post(
        f"/admin/partners/{user['id']}/status", headers=admin_headers,
        json={"status": "approved", "reason": "Документы проверены"},
    )
    assert blocked.status_code == 409
    verified = c.post(
        f"/admin/users/{user['id']}/verify-email", headers=admin_headers,
        json={"reason": "Подтверждено по звонку владельцу"},
    )
    assert verified.status_code == 200
    approved = c.post(
        f"/admin/partners/{user['id']}/status", headers=admin_headers,
        json={"status": "approved", "reason": "Документы проверены"},
    )
    assert approved.status_code == 200 and approved.json()["status"] == "approved"
    assert user["partner_id"] in {p["id"] for p in c.get("/partners").json()}

    created = c.post("/boxes", headers=headers, json=box_payload(user["partner_id"]))
    assert created.status_code == 201
    assert c.get("/partner/me/boxes", headers=headers).status_code == 200


def test_suspension_revokes_sessions_and_removes_active_inventory(client):
    c, _, _, admin_headers = client
    user, headers = register_partner(c)
    c.post(f"/admin/users/{user['id']}/verify-email", headers=admin_headers,
           json={"reason": "Проверено оператором"})
    c.post(f"/admin/partners/{user['id']}/status", headers=admin_headers,
           json={"status": "approved"})
    box = c.post("/boxes", headers=headers, json=box_payload(user["partner_id"])).json()
    assert box["id"] in {b["id"] for b in c.get("/boxes").json()}

    suspended = c.post(
        f"/admin/partners/{user['id']}/status", headers=admin_headers,
        json={"status": "suspended", "reason": "Проверка качества"},
    )
    assert suspended.status_code == 200
    assert box["id"] not in {b["id"] for b in c.get("/boxes").json()}
    assert c.get("/partner/me/orders", headers=headers).status_code == 401
    login = c.post("/auth/login", json={
        "email": "cafe@example.com", "password": "Secret123",
    })
    assert login.status_code == 403
