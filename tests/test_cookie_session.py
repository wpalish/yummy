"""Same-origin HttpOnly cookie session и double-submit CSRF."""
from __future__ import annotations

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

    accounts = Accounts(tmp_path / "accounts.db")
    store = Store(tmp_path / "store.db")
    seed(store)
    monkeypatch.setattr(accounts_mod, "accounts", accounts)
    monkeypatch.setattr(main_mod, "store", store)
    accounts_mod._auth_hits.clear()
    accounts_mod._jail.clear()
    main_mod._rate_hits.clear()
    main_mod._ai_hits.clear()
    return TestClient(main_mod.app)


def register_session(client):
    response = client.post("/session/register", json={
        "email": "cookie@yummy.kz",
        "password": "Secret123",
        "accepted_terms": True,
    })
    assert response.status_code == 201, response.text
    return response


def test_session_tokens_never_enter_json_and_cookie_flags_are_secure(client):
    response = register_session(client)
    body = response.json()
    assert body["auth_mode"] == "cookie" and body["csrf_token"]
    assert "access_token" not in body and "refresh_token" not in body

    cookies = response.headers.get_list("set-cookie")
    access = next(c for c in cookies if c.startswith("yummy_access="))
    refresh = next(c for c in cookies if c.startswith("yummy_refresh="))
    csrf = next(c for c in cookies if c.startswith("yummy_csrf="))
    assert "HttpOnly" in access and "SameSite=strict" in access and "Path=/" in access
    assert "HttpOnly" in refresh and "SameSite=strict" in refresh and "Path=/session" in refresh
    assert "HttpOnly" not in csrf and "SameSite=strict" in csrf
    assert client.get("/session/me").status_code == 200


def test_cookie_mutation_requires_matching_csrf(client):
    response = register_session(client)
    box_id = client.get("/boxes").json()[0]["id"]
    payload = {"box_id": box_id, "user_name": "Айша", "user_phone": "+77001234567"}

    denied = client.post("/orders", json=payload)
    assert denied.status_code == 403 and "CSRF" in denied.json()["detail"]

    allowed = client.post(
        "/orders", json=payload, headers={"X-CSRF-Token": response.json()["csrf_token"]}
    )
    assert allowed.status_code == 201
    assert len(client.get("/me/orders").json()) == 1


def test_refresh_rotates_http_only_session_and_requires_csrf(client):
    response = register_session(client)
    csrf = response.json()["csrf_token"]
    client.cookies.delete("yummy_access")  # simulate 15-minute access expiry
    assert client.get("/session/me").status_code == 401

    assert client.post("/session/refresh").status_code == 403
    refreshed = client.post("/session/refresh", headers={"X-CSRF-Token": csrf})
    assert refreshed.status_code == 200
    assert refreshed.json()["csrf_token"] != csrf
    assert client.get("/session/me").status_code == 200


def test_logout_revokes_refresh_and_clears_cookies(client):
    response = register_session(client)
    csrf = response.json()["csrf_token"]
    raw_refresh = client.cookies["yummy_refresh"]
    logged_out = client.post("/session/logout", headers={"X-CSRF-Token": csrf})
    assert logged_out.status_code == 200
    assert "yummy_access" not in client.cookies
    assert "yummy_refresh" not in client.cookies
    assert client.get("/session/me").status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": raw_refresh}).status_code == 401


def test_cookie_change_password_rotates_session_without_exposing_tokens(client):
    session = register_session(client)
    changed = client.post(
        "/session/change-password",
        headers={"X-CSRF-Token": session.json()["csrf_token"]},
        json={"old_password": "Secret123", "new_password": "Newpass123"},
    )
    assert changed.status_code == 200
    assert "access_token" not in changed.json() and "refresh_token" not in changed.json()
    assert client.get("/session/me").status_code == 200


def test_cookie_session_rejects_cross_origin_mutation(client):
    response = register_session(client)
    denied = client.post(
        "/session/logout",
        headers={
            "X-CSRF-Token": response.json()["csrf_token"],
            "Origin": "https://evil.example",
        },
    )
    assert denied.status_code == 403 and "Origin" in denied.json()["detail"]


def test_bearer_api_remains_cookie_independent(client):
    session = register_session(client)
    bearer = client.post(
        "/auth/login",
        headers={"X-CSRF-Token": session.json()["csrf_token"]},
        json={"email": "cookie@yummy.kz", "password": "Secret123"},
    ).json()["access_token"]
    box_id = client.get("/boxes").json()[0]["id"]
    response = client.post(
        "/orders",
        headers={"Authorization": f"Bearer {bearer}"},
        json={"box_id": box_id, "user_name": "Айша", "user_phone": "+77001234567"},
    )
    assert response.status_code == 201
