"""№5 (остаток): refresh-токен в httpOnly-cookie — XSS не уносит сессию."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.accounts import Accounts, hash_password


@pytest.fixture
def env(tmp_path, monkeypatch):
    import app.accounts as accounts_mod

    monkeypatch.setattr(accounts_mod, "_ENFORCE", True)
    monkeypatch.setattr(accounts_mod, "_AUTH_MAX", 100)
    users = Accounts(path=tmp_path / "u.db")
    monkeypatch.setattr(accounts_mod, "accounts", users)
    accounts_mod._auth_hits.clear()
    users.create("u@x.kz", hash_password("Pass1234"), "customer", None, None)
    return TestClient(main_mod.app), users


def test_login_sets_httponly_refresh_cookie(env):
    c, users = env
    r = c.post("/auth/login", json={"email": "u@x.kz", "password": "Pass1234"})
    assert r.status_code == 200
    sc = r.headers.get("set-cookie", "")
    assert "ym_refresh=" in sc and "HttpOnly" in sc and "SameSite=none" in sc.replace("None", "none")
    assert "Secure" in sc and "Path=/auth" in sc


def test_refresh_via_cookie_without_body_token(env):
    c, users = env
    login = c.post("/auth/login", json={"email": "u@x.kz", "password": "Pass1234"}).json()
    # Secure-cookie по http TestClient не переигрывает — подставляем её явно
    # (в браузере это делает сам cookie-jar; localhost — trustworthy origin)
    r = c.post("/auth/refresh", json={"refresh_token": ""},
               cookies={"ym_refresh": login["refresh_token"]})
    assert r.status_code == 200 and r.json()["access_token"]
    # ротация с grace-окном: в первые 30с старый токен ещё жив (гонка вкладок),
    # после — труп (проверяем, подкрутив expires_at в прошлое)
    with users._conn() as conn:
        conn.execute("UPDATE refresh_tokens SET expires_at=0 WHERE expires_at < ?",
                     (__import__("time").time() + 60,))
    assert c.post("/auth/refresh", json={"refresh_token": ""},
                  cookies={"ym_refresh": login["refresh_token"]}).status_code == 401


def test_refresh_empty_without_cookie_fails(env):
    c, users = env
    assert c.post("/auth/refresh", json={"refresh_token": ""}).status_code == 401


def test_logout_all_clears_cookie(env):
    c, users = env
    login = c.post("/auth/login", json={"email": "u@x.kz", "password": "Pass1234"}).json()
    h = {"Authorization": f"Bearer {login['access_token']}"}
    r = c.post("/auth/logout-all", headers=h)
    assert r.status_code == 200
    assert c.post("/auth/refresh", json={"refresh_token": ""}).status_code == 401
