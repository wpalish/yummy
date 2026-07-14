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
    import app.main as main_mod
    from fastapi.testclient import TestClient
    from app.db import Store
    from app.main import app
    from app.seed import seed

    monkeypatch.setattr(accounts_mod, "accounts", Accounts(path=tmp_path / "api.db"))
    # app.main.store — модульный синглтон, общий на все тесты процесса: без
    # подмены заказы из разных тестов делят один и тот же посевной инвентарь и
    # к концу сьюта боксы раскупаются («list index out of range» на /boxes).
    fresh_store = Store(path=tmp_path / "store.db")
    seed(fresh_store)
    monkeypatch.setattr(main_mod, "store", fresh_store)
    # изоляция между тестами: rate-limit и jail общие по IP/email —
    # без сброса набегает 429 при быстром прогоне всего сьюта
    accounts_mod._auth_hits.clear()
    accounts_mod._jail.clear()
    main_mod._rate_hits.clear()
    main_mod._ai_hits.clear()
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


# ---- отзыв сессий и fail-fast конфиг ---------------------------------------- #
def test_change_password_revokes_old_tokens(tmp_path, monkeypatch):
    """Смена пароля отзывает ВСЕ старые токены; ответ содержит свежий."""
    c = _client(tmp_path, monkeypatch)
    old_tok = c.post("/auth/register", json={"email": "rv@yummy.kz", "password": "Secret123"}).json()["access_token"]
    assert c.get("/auth/me", headers={"Authorization": f"Bearer {old_tok}"}).status_code == 200

    r = c.post("/auth/change-password", headers={"Authorization": f"Bearer {old_tok}"},
               json={"old_password": "Secret123", "new_password": "Newpass123"})
    assert r.status_code == 200
    new_tok = r.json()["access_token"]

    dead = c.get("/auth/me", headers={"Authorization": f"Bearer {old_tok}"})
    assert dead.status_code == 401                       # украденный токен мёртв
    alive = c.get("/auth/me", headers={"Authorization": f"Bearer {new_tok}"})
    assert alive.status_code == 200                      # текущее устройство живо


def test_prod_config_fail_fast(monkeypatch):
    import app.accounts as A

    monkeypatch.setenv("YUMMY_ENFORCE_AUTH", "1")
    monkeypatch.setattr(A, "_SECRET", A._DEFAULT_SECRET)
    with pytest.raises(RuntimeError, match="YUMMY_SECRET_KEY"):
        A.assert_prod_config()
    monkeypatch.setattr(A, "_SECRET", "real-secret-0123456789abcdef")
    A.assert_prod_config()  # с настоящим секретом — ок


# ---- Sentinel-пак: refresh-ротация, logout-all, privacy --------------------- #
def test_pbkdf2_backward_compatible_rounds():
    """Старые хеши (200k) верифицируются — rounds читаются из записи."""
    import hashlib as hl
    import secrets as sec
    salt = sec.token_bytes(16)
    dk = hl.pbkdf2_hmac("sha256", b"Secret123", salt, 200_000)
    legacy = f"pbkdf2_sha256$200000${salt.hex()}${dk.hex()}"
    assert verify_password("Secret123", legacy)


def test_refresh_rotation(tmp_path, monkeypatch):
    """Refresh обновляет access; использованный refresh сгорает (ротация)."""
    c = _client(tmp_path, monkeypatch)
    r = c.post("/auth/register", json={"email": "rf@yummy.kz", "password": "Secret123"}).json()
    assert r["refresh_token"]
    r2 = c.post("/auth/refresh", json={"refresh_token": r["refresh_token"]})
    assert r2.status_code == 200
    assert c.get("/auth/me", headers={"Authorization": f"Bearer {r2.json()['access_token']}"}).status_code == 200
    # старый refresh уже отозван ротацией
    assert c.post("/auth/refresh", json={"refresh_token": r["refresh_token"]}).status_code == 401


def test_logout_all_revokes_everything(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/auth/register", json={"email": "la@yummy.kz", "password": "Secret123"}).json()
    tok, ref = r["access_token"], r["refresh_token"]
    assert c.post("/auth/logout-all", headers={"Authorization": f"Bearer {tok}"}).status_code == 200
    assert c.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    assert c.post("/auth/refresh", json={"refresh_token": ref}).status_code == 401


def test_export_and_delete_me(tmp_path, monkeypatch):
    """Privacy: экспорт данных и удаление аккаунта с обезличиванием заказов."""
    c = _client(tmp_path, monkeypatch)
    tok = c.post("/auth/register", json={"email": "pr@yummy.kz", "password": "Secret123"}).json()["access_token"]
    bid = c.get("/boxes").json()[0]["id"]
    code = c.post("/orders", json={"box_id": bid, "user_name": "Алишер", "user_phone": "+77010000000"},
                  headers={"Authorization": f"Bearer {tok}"}).json()["order"]["code"]

    exp = c.get("/me/export", headers={"Authorization": f"Bearer {tok}"}).json()
    assert exp["profile"]["email"] == "pr@yummy.kz"
    assert any(o["code"] == code for o in exp["orders"])
    assert "pw_hash" not in str(exp)

    d = c.delete("/me", headers={"Authorization": f"Bearer {tok}"})
    assert d.status_code == 200 and d.json()["orders_anonymized"] == 1
    # вход невозможен, токен отозван, PII обезличен
    assert c.post("/auth/login", json={"email": "pr@yummy.kz", "password": "Secret123"}).status_code == 401
    assert c.get("/auth/me", headers={"Authorization": f"Bearer {tok}"}).status_code == 401
    pub = c.get(f"/orders/{code}").json()
    assert pub["user_name"] == "(удалён)" and pub["user_phone"] == ""


# ---- AI-фичи: описание бокса, рекомендации, отзывы -------------------------- #
def test_describe_box_fallback_without_key(tmp_path, monkeypatch):
    """Без ANTHROPIC_API_KEY — детерминированный фолбэк, не 501/ошибка."""
    c = _client(tmp_path, monkeypatch)
    r = c.post("/ai/describe-box", json={"category": "sweet", "notes": "2 круассана, маффин"})
    assert r.status_code == 200
    body = r.json()
    assert body["ai"] is False and "круассана" in body["description"]


def test_describe_box_rejects_empty_notes(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    r = c.post("/ai/describe-box", json={"category": "sweet", "notes": ""})
    assert r.status_code == 422  # Pydantic min_length


def test_recommendations_requires_auth(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    assert c.get("/me/recommendations").status_code == 401


def test_recommendations_returns_boxes(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    tok = c.post("/auth/register", json={"email": "rec@yummy.kz", "password": "Secret123"}).json()["access_token"]
    r = c.get("/me/recommendations", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 200
    assert 0 < len(r.json()) <= 4


def test_review_full_flow(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    tok = c.post("/auth/register", json={"email": "rv@yummy.kz", "password": "Secret123"}).json()["access_token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    box = c.get("/boxes").json()[0]
    order = c.post("/orders", json={"box_id": box["id"], "user_name": "Т", "user_phone": "+77010000000"},
                   headers=hdr).json()["order"]

    # заказ ещё не выдан — отзыв рано
    bad = c.post(f"/partners/{box['partner_id']}/reviews",
                 json={"order_id": order["id"], "rating": 5, "text": "Отличный бокс!"}, headers=hdr)
    assert bad.status_code == 409

    assert c.post("/redeem", json={"code": order["code"]}).json()["ok"] is True

    ok = c.post(f"/partners/{box['partner_id']}/reviews",
               json={"order_id": order["id"], "rating": 5, "text": "Отличный бокс, всё свежее!"}, headers=hdr)
    assert ok.status_code == 201 and ok.json()["status"] == "approved"

    # повторный отзыв на тот же заказ — нельзя
    dup = c.post(f"/partners/{box['partner_id']}/reviews",
                json={"order_id": order["id"], "rating": 4, "text": "Ещё раз попробовал"}, headers=hdr)
    assert dup.status_code == 409

    listed = c.get(f"/partners/{box['partner_id']}/reviews").json()
    assert any(r["order_id"] == order["id"] for r in listed)


def test_review_blocked_by_moderation(tmp_path, monkeypatch):
    c = _client(tmp_path, monkeypatch)
    tok = c.post("/auth/register", json={"email": "rv2@yummy.kz", "password": "Secret123"}).json()["access_token"]
    hdr = {"Authorization": f"Bearer {tok}"}
    box = c.get("/boxes").json()[0]
    order = c.post("/orders", json={"box_id": box["id"], "user_name": "Т", "user_phone": "+77010000000"},
                   headers=hdr).json()["order"]
    c.post("/redeem", json={"code": order["code"]})
    r = c.post(f"/partners/{box['partner_id']}/reviews",
              json={"order_id": order["id"], "rating": 1, "text": "полная хуйня а не бокс"}, headers=hdr)
    assert r.status_code == 422


def test_review_rejects_other_users_order(tmp_path, monkeypatch):
    """Чужой order_id — нельзя оставить отзыв (проверка через user_orders(), не тело запроса)."""
    c = _client(tmp_path, monkeypatch)
    tok1 = c.post("/auth/register", json={"email": "owner@yummy.kz", "password": "Secret123"}).json()["access_token"]
    tok2 = c.post("/auth/register", json={"email": "intruder@yummy.kz", "password": "Secret123"}).json()["access_token"]
    box = c.get("/boxes").json()[0]
    order = c.post("/orders", json={"box_id": box["id"], "user_name": "Т", "user_phone": "+77010000000"},
                   headers={"Authorization": f"Bearer {tok1}"}).json()["order"]
    c.post("/redeem", json={"code": order["code"]})
    r = c.post(f"/partners/{box['partner_id']}/reviews",
              json={"order_id": order["id"], "rating": 5, "text": "Пытаюсь оставить чужой отзыв"},
              headers={"Authorization": f"Bearer {tok2}"})
    assert r.status_code == 404
