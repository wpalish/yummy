"""Регистрация с кодом из письма: аккаунт создаётся только после подтверждения.
Без SMTP — как раньше (graceful degradation, пилот не ломается)."""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from app import mailer
from app import main as main_mod
from app.accounts import Accounts


@pytest.fixture
def env(tmp_path, monkeypatch):
    import app.accounts as accounts_mod

    users = Accounts(path=tmp_path / "u.db")
    monkeypatch.setattr(accounts_mod, "accounts", users)
    monkeypatch.setattr(accounts_mod, "_AUTH_MAX", 100)
    accounts_mod._auth_hits.clear()
    sent: list[dict] = []
    monkeypatch.setattr(mailer, "is_configured", lambda: True)
    monkeypatch.setattr(mailer, "send",
                        lambda to, subject, body: sent.append({"to": to, "body": body}) or True)
    return TestClient(main_mod.app), users, sent


def _code_from(sent) -> str:
    return re.search(r"\b(\d{6})\b", sent[-1]["body"]).group(1)


def test_register_requires_code_then_creates_account(env):
    c, users, sent = env
    r = c.post("/auth/register", json={"email": "v@x.kz", "password": "Pass1234"})
    assert r.status_code == 201 and r.json()["status"] == "verify"
    assert users.by_email("v@x.kz") is None          # аккаунта ещё НЕТ
    assert sent and sent[-1]["to"] == "v@x.kz"

    code = _code_from(sent)
    # неверный код — не проходит
    assert c.post("/auth/verify-email",
                  json={"email": "v@x.kz", "code": "000000" if code != "000000" else "111111"}
                  ).status_code == 400
    # верный — аккаунт создан, токены выданы
    ok = c.post("/auth/verify-email", json={"email": "v@x.kz", "code": code})
    assert ok.status_code == 201 and ok.json()["access_token"]
    assert users.by_email("v@x.kz")["role"] == "customer"
    # код одноразовый
    assert c.post("/auth/verify-email",
                  json={"email": "v@x.kz", "code": code}).status_code == 409


def test_attempts_limit_burns_pending(env):
    c, users, sent = env
    c.post("/auth/register", json={"email": "b@x.kz", "password": "Pass1234"})
    code = _code_from(sent)
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        c.post("/auth/verify-email", json={"email": "b@x.kz", "code": wrong})
    # после 5 неудач даже верный код сгорел — перебор 6 цифр не работает
    assert c.post("/auth/verify-email",
                  json={"email": "b@x.kz", "code": code}).status_code == 400


def test_reregister_resends_new_code(env):
    c, users, sent = env
    c.post("/auth/register", json={"email": "r@x.kz", "password": "Pass1234"})
    old = _code_from(sent)
    c.post("/auth/register", json={"email": "r@x.kz", "password": "Pass1234"})
    new = _code_from(sent)
    assert len(sent) == 2
    # старый код погашен перезаписью — работает только новый
    if old != new:
        assert c.post("/auth/verify-email",
                      json={"email": "r@x.kz", "code": old}).status_code == 400
    assert c.post("/auth/verify-email",
                  json={"email": "r@x.kz", "code": new}).status_code == 201


def test_without_smtp_registers_immediately(env, monkeypatch):
    c, users, sent = env
    monkeypatch.setattr(mailer, "is_configured", lambda: False)
    r = c.post("/auth/register", json={"email": "i@x.kz", "password": "Pass1234"})
    assert r.status_code == 201 and r.json()["access_token"]   # как раньше
    assert users.by_email("i@x.kz") is not None
    assert not sent                                            # письмо не слалось


def test_smtp_send_failure_falls_back(env, monkeypatch):
    """SMTP настроен, но провайдер упал — регистрация не блокируется."""
    c, users, sent = env
    monkeypatch.setattr(mailer, "send", lambda *a: False)
    r = c.post("/auth/register", json={"email": "f@x.kz", "password": "Pass1234"})
    assert r.status_code == 201 and r.json().get("access_token")
    assert users.by_email("f@x.kz") is not None
