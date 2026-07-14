"""Email verification and password recovery token lifecycle."""
from __future__ import annotations

import re

import pytest

import app.accounts as A
import app.email_delivery as mail
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
    monkeypatch.setattr(mail, "_MODE", "development")
    monkeypatch.setattr(mail, "_PRODUCTION", False)
    mail._DEV_OUTBOX.clear()
    A._auth_hits.clear()
    A._jail.clear()
    main_mod._rate_hits.clear()
    main_mod._ai_hits.clear()
    return TestClient(main_mod.app), accounts


def _token_from_last_email(param: str) -> str:
    text = mail._DEV_OUTBOX[-1]["text"]
    match = re.search(rf"[?&]{param}=([^\s]+)", text)
    assert match
    return match.group(1)


def register(c, email="buyer@example.com"):
    return c.post("/auth/register", json={
        "email": email, "password": "Secret123", "accepted_terms": True,
    })


def test_verification_token_is_hashed_single_use_and_updates_profile(client):
    c, accounts = client
    registered = register(c)
    assert registered.status_code == 201
    assert registered.json()["user"]["email_verified"] is False
    raw = _token_from_last_email("verify")
    with accounts._conn() as conn:
        stored = conn.execute(
            "SELECT token_hash FROM action_tokens WHERE purpose='verify_email'"
        ).fetchone()[0]
    assert raw not in stored

    confirmed = c.post("/auth/email/verify/confirm", json={"token": raw})
    assert confirmed.status_code == 200
    assert accounts.by_email("buyer@example.com")["email_verified"] == 1
    assert c.post("/auth/email/verify/confirm", json={"token": raw}).status_code == 400


def test_reissuing_verification_invalidates_previous_token(client):
    c, _ = client
    registered = register(c)
    old = _token_from_last_email("verify")
    token = registered.json()["access_token"]
    requested = c.post(
        "/auth/email/verify/request", headers={"Authorization": f"Bearer {token}"}
    )
    assert requested.status_code == 202
    new = _token_from_last_email("verify")
    assert old != new
    assert c.post("/auth/email/verify/confirm", json={"token": old}).status_code == 400
    assert c.post("/auth/email/verify/confirm", json={"token": new}).status_code == 200


def test_forgot_password_is_non_enumerating_and_reset_revokes_sessions(client):
    c, _ = client
    registered = register(c)
    refresh = registered.json()["refresh_token"]
    before = len(mail._DEV_OUTBOX)
    unknown = c.post("/auth/password/forgot", json={"email": "unknown@example.com"})
    assert unknown.status_code == 202 and unknown.json() == {"status": "accepted"}
    assert len(mail._DEV_OUTBOX) == before

    known = c.post("/auth/password/forgot", json={"email": "buyer@example.com"})
    assert known.status_code == 202 and known.json() == unknown.json()
    raw = _token_from_last_email("reset")
    reset = c.post("/auth/password/reset", json={
        "token": raw, "new_password": "Newpass123",
    })
    assert reset.status_code == 200 and reset.json()["sessions_revoked"] is True
    assert c.post("/auth/password/reset", json={
        "token": raw, "new_password": "Againpass123",
    }).status_code == 400
    A._auth_hits.clear()
    assert c.post("/auth/refresh", json={"refresh_token": refresh}).status_code == 401
    assert c.post("/auth/login", json={
        "email": "buyer@example.com", "password": "Secret123",
    }).status_code == 401
    assert c.post("/auth/login", json={
        "email": "buyer@example.com", "password": "Newpass123",
    }).status_code == 200


def test_expired_action_token_is_rejected(client):
    c, accounts = client
    registered = register(c)
    uid = registered.json()["user"]["id"]
    expired = accounts.issue_action_token(uid, "verify_email", -1)
    assert c.post("/auth/email/verify/confirm", json={"token": expired}).status_code == 400


def test_production_rejects_development_email_outbox(monkeypatch):
    monkeypatch.setattr(mail, "_PRODUCTION", True)
    monkeypatch.setattr(mail, "_MODE", "development")
    with pytest.raises(RuntimeError, match="development email outbox"):
        mail.assert_email_config()
