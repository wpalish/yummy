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
