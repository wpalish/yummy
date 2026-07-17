"""Invitation-only partner owner/manager/cashier access."""
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
    token = A.create_token(admin_id, "admin", ver=row["token_ver"], mfa_verified=True)
    return TestClient(main_mod.app), accounts, {"Authorization": f"Bearer {token}"}


def invite(c, admin, payload):
    response = c.post("/admin/staff-invitations", headers=admin, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["invite_url"].split("invite=", 1)[1]


def accept(c, token, password="Secret123"):
    return c.post("/auth/invitations/accept", json={
        "token": token, "password": password, "accepted_terms": True,
    })


def test_owner_invitation_is_single_use_and_creates_approved_tenant(client):
    c, accounts, admin = client
    token = invite(c, admin, {
        "email": "owner@cafe.kz", "partner_role": "owner",
        "brand_name": "Invite Cafe", "address": "ул. 1", "district": "Нура",
    })
    with accounts._conn() as connection:
        stored = connection.execute("SELECT token_hash FROM staff_invitations").fetchone()[0]
    assert token not in stored
    accepted = accept(c, token)
    assert accepted.status_code == 200
    user = accepted.json()["user"]
    assert user["partner_role"] == "owner" and user["partner_status"] == "approved"
    headers = {"Authorization": f"Bearer {accepted.json()['access_token']}"}
    profile = c.get("/partner/me", headers=headers)
    assert profile.status_code == 200 and profile.json()["name"] == "Invite Cafe"
    assert accept(c, token).status_code == 400


def test_cashier_is_bound_to_partner_and_cannot_publish(client):
    c, _, admin = client
    owner_token = invite(c, admin, {
        "email": "owner2@cafe.kz", "partner_role": "owner",
        "brand_name": "Cafe 2", "address": "ул. 2", "district": "Нура",
    })
    owner = accept(c, owner_token).json()
    owner_headers = {"Authorization": f"Bearer {owner['access_token']}"}
    partner_id = c.get("/partner/me", headers=owner_headers).json()["id"]

    cashier_token = invite(c, admin, {
        "email": "cashier@cafe.kz", "partner_role": "cashier", "partner_id": partner_id,
    })
    cashier = accept(c, cashier_token).json()
    assert cashier["user"]["partner_id"] == partner_id
    cashier_headers = {"Authorization": f"Bearer {cashier['access_token']}"}
    assert c.get("/partner/me/orders", headers=cashier_headers).status_code == 200
    assert c.post("/boxes", headers=cashier_headers, json={
        "partner_id": partner_id, "category": "sweet", "price": 500,
        "value_est": 1000, "qty": 1,
        "pickup_from": "2030-01-01T10:00:00+00:00",
        "pickup_to": "2030-01-01T12:00:00+00:00",
    }).status_code == 403


def test_public_partner_registration_is_blocked_in_production(client, monkeypatch):
    c, _, _ = client
    monkeypatch.setattr(A, "_PRODUCTION", True)
    response = c.post("/auth/register", json={
        "email": "public@cafe.kz", "password": "Secret123", "role": "partner",
        "brand_name": "Nope", "address": "ул. 1", "accepted_terms": True,
    })
    assert response.status_code == 403
