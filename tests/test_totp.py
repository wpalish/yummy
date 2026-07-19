"""TOTP-2FA (RFC 6238 на stdlib): алгоритм, включение, вход, выключение."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import totp
from app import main as main_mod
from app.accounts import Accounts, create_token, hash_password


# --------------------------------------------------------------------------- #
#  Алгоритм — контрольный вектор RFC 6238 (SHA-1, тестовый секрет "12345678901234567890")
# --------------------------------------------------------------------------- #
def test_rfc6238_vector():
    import base64
    secret = base64.b32encode(b"12345678901234567890").decode()
    assert totp.code_at(secret, t=59) == "287082"          # из приложения RFC
    assert totp.code_at(secret, t=1111111109) == "081804"


def test_verify_window_and_garbage():
    s = totp.new_secret()
    import time
    now = time.time()
    assert totp.verify(s, totp.code_at(s, now))
    assert totp.verify(s, totp.code_at(s, now - 30))       # дрейф часов ±1 шаг
    assert not totp.verify(s, "000000") or totp.code_at(s, now) == "000000"
    assert not totp.verify(s, "12345")                     # не 6 цифр
    assert not totp.verify(s, "abcdef")


# --------------------------------------------------------------------------- #
#  Флоу: включение → вход требует код → выключение
# --------------------------------------------------------------------------- #
@pytest.fixture
def env(tmp_path, monkeypatch):
    import app.accounts as accounts_mod

    monkeypatch.setattr(accounts_mod, "_ENFORCE", True)
    monkeypatch.setattr(accounts_mod, "_AUTH_MAX", 100)   # флоу делает ~10 auth-вызовов
    users = Accounts(path=tmp_path / "u.db")
    monkeypatch.setattr(accounts_mod, "accounts", users)
    accounts_mod._auth_hits.clear()
    main_mod._rate_hits.clear()
    return TestClient(main_mod.app), users


def test_full_2fa_flow(env):
    c, users = env
    uid = users.create("boss@x.kz", hash_password("Pass1234"), "admin", None, None)
    h = {"Authorization": f"Bearer {create_token(uid, 'admin')}"}

    # setup → enable с живым кодом
    s = c.post("/auth/totp/setup", headers=h).json()
    assert s["secret"] and "otpauth://" in s["otpauth"] and "<svg" in s["qr_svg"]
    code = totp.code_at(s["secret"])
    assert c.post("/auth/totp/enable", headers=h,
                  json={"secret": s["secret"], "code": code}).status_code == 200
    # секрет в БД зашифрован
    with users._conn() as conn:
        raw = conn.execute("SELECT totp_secret FROM users WHERE id=?", (uid,)).fetchone()[0]
    assert raw.startswith("enc1:") and s["secret"] not in raw

    # вход: пароль без кода → totp_required; с кодом → ок
    r = c.post("/auth/login", json={"email": "boss@x.kz", "password": "Pass1234"})
    assert r.status_code == 401 and r.json()["detail"] == "totp_required"
    r = c.post("/auth/login", json={"email": "boss@x.kz", "password": "Pass1234",
                                    "totp": totp.code_at(s["secret"])})
    assert r.status_code == 200 and r.json()["access_token"]
    # неверный код → 401 (и кормит jail)
    r = c.post("/auth/login", json={"email": "boss@x.kz", "password": "Pass1234",
                                    "totp": "000001"})
    assert r.status_code == 401

    # выключение только с валидным кодом
    assert c.post("/auth/totp/disable", headers=h,
                  json={"code": "999999"}).status_code == 400
    assert c.post("/auth/totp/disable", headers=h,
                  json={"code": totp.code_at(s["secret"])}).status_code == 200
    assert c.post("/auth/login", json={"email": "boss@x.kz",
                                       "password": "Pass1234"}).status_code == 200


def test_enable_rejects_wrong_code(env):
    c, users = env
    uid = users.create("u@x.kz", "x", "customer", None, None)
    h = {"Authorization": f"Bearer {create_token(uid, 'customer')}"}
    s = c.post("/auth/totp/setup", headers=h).json()
    assert c.post("/auth/totp/enable", headers=h,
                  json={"secret": s["secret"], "code": "000001"}).status_code == 400
    assert users.totp_secret(uid) is None              # не включилась


def test_admin_requires_2fa_enrolled(env, monkeypatch):
    """Обязательная 2FA: админ без TOTP не проходит в админ-эндпоинты,
    но /auth/totp/* доступны — включить её он может всегда."""
    monkeypatch.delenv("YUMMY_ADMIN_2FA_OPTIONAL", raising=False)
    c, users = env
    uid = users.create("noweak@x.kz", "x", "admin", None, None)
    h = {"Authorization": f"Bearer {create_token(uid, 'admin')}"}
    r = c.get("/admin/users", headers=h)
    assert r.status_code == 403 and "2FA" in r.json()["detail"]
    assert c.post("/auth/totp/setup", headers=h).status_code == 200  # путь к включению открыт
    # включил — доступ появился
    s = c.post("/auth/totp/setup", headers=h).json()
    c.post("/auth/totp/enable", headers=h,
           json={"secret": s["secret"], "code": totp.code_at(s["secret"])})
    assert c.get("/admin/users", headers=h).status_code == 200
