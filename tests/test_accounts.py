"""Тесты регистрации/входа: хеширование пароля, JWT, полный флоу через API."""
from __future__ import annotations

import time

import pytest

from app.accounts import (
    Accounts,
    create_token,
    decode_token,
    hash_password,
    verify_password,
)


# ---- пароль: PBKDF2 + соль (без внешних зависимостей) --------------------- #
def test_password_roundtrip():
    h = hash_password("Secret123")
    assert verify_password("Secret123", h)
    assert not verify_password("wrong123", h)


def test_password_hash_is_salted():
    """Один пароль → разные хеши (случайная соль), в хеше нет самого пароля."""
    a, b = hash_password("Secret123"), hash_password("Secret123")
    assert a != b
    assert "Secret123" not in a


def test_verify_rejects_garbage():
    assert not verify_password("x", "not-a-valid-hash")


# ---- JWT HS256 (stdlib) --------------------------------------------------- #
def test_jwt_roundtrip():
    tok = create_token("u1", "customer")
    data = decode_token(tok)
    assert data["sub"] == "u1" and data["role"] == "customer"


def test_jwt_tamper_detected():
    tok = create_token("u1", "customer")
    head, payload, _sig = tok.split(".")
    forged = f"{head}.{payload}.{'A' * 43}"
    with pytest.raises(ValueError, match="подпис"):
        decode_token(forged)


def test_jwt_expired():
    tok = create_token("u1", "customer", ttl=-10)
    with pytest.raises(ValueError, match="истёк"):
        decode_token(tok)


# ---- хранилище ------------------------------------------------------------ #
def test_accounts_create_and_lookup(tmp_path):
    acc = Accounts(path=tmp_path / "u.db")
    uid = acc.create("a@b.kz", hash_password("Secret123"), "customer", None, None)
    assert acc.by_id(uid)["email"] == "a@b.kz"
    assert acc.by_email("A@B.KZ")["id"] == uid  # регистронезависимо


# ---- полный флоу через API (нужен httpx → в CI; локально пропуск) ---------- #
def _client(tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    import app.accounts as accounts_mod
    from fastapi.testclient import TestClient
    from app.main import app

    monkeypatch.setattr(accounts_mod, "accounts", Accounts(path=tmp_path / "api.db"))
    # изоляция между тестами: rate-limit и jail общие по IP/email —
    # без сброса набегает 429 при быстром прогоне всего сьюта
    accounts_mod._auth_hits.clear()
    accounts_mod._jail.clear()
    return TestClient(app)


def test_register_login_flow(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/auth/register", json={"email": "buyer@yummy.kz", "password": "Secret123"})
    assert r.status_code == 201
    body = r.json()
    assert body["user"]["role"] == "customer"
    assert "pw_hash" not in str(body)          # хеш пароля не утекает в ответ
    assert body["access_token"]

    r2 = c.post("/auth/login", json={"email": "buyer@yummy.kz", "password": "Secret123"})
    assert r2.status_code == 200
    token = r2.json()["access_token"]

    me = c.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200 and me.json()["email"] == "buyer@yummy.kz"


def test_duplicate_email_rejected(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.post("/auth/register", json={"email": "dup@yummy.kz", "password": "Secret123"})
    r = c.post("/auth/register", json={"email": "dup@yummy.kz", "password": "Secret123"})
    assert r.status_code == 409


def test_weak_password_rejected(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/auth/register", json={"email": "x@yummy.kz", "password": "short"})
    assert r.status_code == 422


def test_wrong_password_rejected(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    c.post("/auth/register", json={"email": "y@yummy.kz", "password": "Secret123"})
    r = c.post("/auth/login", json={"email": "y@yummy.kz", "password": "Nope1234"})
    assert r.status_code == 401


def test_partner_requires_brand(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/auth/register", json={
        "email": "cafe@yummy.kz", "password": "Secret123", "role": "partner"})
    assert r.status_code == 422
    r2 = c.post("/auth/register", json={
        "email": "cafe@yummy.kz", "password": "Secret123", "role": "partner",
        "brand_name": "Coffee Point", "address": "пр. Мангилик Ел, 55"})
    assert r2.status_code == 201 and r2.json()["user"]["brand_name"] == "Coffee Point"


# ---- iss-клейм (spring-security паттерн) и login-jail (xapax) --------------- #
def test_jwt_rejects_wrong_issuer():
    """Токен с чужим iss, но валидной подписью — отклоняется."""
    import base64, hashlib as hl, hmac as hm, json as js
    from app.accounts import _SECRET, decode_token
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=").decode()
    head = b64(b'{"alg":"HS256","typ":"JWT"}')
    pay = b64(js.dumps({"iss": "evil", "sub": "u1", "role": "admin",
                        "exp": int(time.time()) + 999}).encode())
    sig = b64(hm.new(_SECRET.encode(), f"{head}.{pay}".encode(), hl.sha256).digest())
    with pytest.raises(ValueError, match="издател"):
        decode_token(f"{head}.{pay}.{sig}")


def test_login_jail_locks_after_fails():
    from fastapi import HTTPException
    from app.accounts import _jail, _jail_check, _jail_fail, _jail_reset

    email = "jail@test.kz"
    _jail_reset(email)
    for _ in range(4):
        _jail_fail(email)
    _jail_check(email)                       # 4 неудачи — ещё не блок
    _jail_fail(email)                        # 5-я — блок
    with pytest.raises(HTTPException) as exc:
        _jail_check(email)
    assert exc.value.status_code == 429
    _jail_reset(email)                       # успешный вход снимает блок
    _jail_check(email)


# ---- production-фичи: admin-роль, смена пароля, /me/orders ------------------ #
def test_admin_email_gets_admin_role(tmp_path, monkeypatch):
    import app.accounts as A
    c = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(A, "_ADMIN_EMAILS", {"boss@yummy.kz"})
    r = c.post("/auth/register", json={"email": "boss@yummy.kz", "password": "Secret123"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "admin"


def test_change_password_flow(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    tok = c.post("/auth/register", json={"email": "cp@yummy.kz", "password": "Secret123"}).json()["access_token"]
    bad = c.post("/auth/change-password", headers={"Authorization": f"Bearer {tok}"},
                 json={"old_password": "WRONG999", "new_password": "Newpass123"})
    assert bad.status_code == 401
    ok = c.post("/auth/change-password", headers={"Authorization": f"Bearer {tok}"},
                json={"old_password": "Secret123", "new_password": "Newpass123"})
    assert ok.status_code == 200
    assert c.post("/auth/login", json={"email": "cp@yummy.kz", "password": "Newpass123"}).status_code == 200


def test_me_orders_cross_device(tmp_path, monkeypatch):
    """Заказ с токеном привязан к аккаунту и виден в /me/orders."""
    c = _client(tmp_path, monkeypatch)
    tok = c.post("/auth/register", json={"email": "mo@yummy.kz", "password": "Secret123"}).json()["access_token"]
    bid = c.get("/boxes").json()[0]["id"]
    r = c.post("/orders", json={"box_id": bid, "user_name": "Т", "user_phone": "+77010000000"},
               headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 201
    mine = c.get("/me/orders", headers={"Authorization": f"Bearer {tok}"}).json()
    assert len(mine) == 1 and mine[0]["code"] == r.json()["order"]["code"]
    assert c.get("/me/orders").status_code == 401  # без токена — закрыто
