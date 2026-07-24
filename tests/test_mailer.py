"""mailer: выбор транспорта (Resend HTTP приоритетнее SMTP) и graceful degradation.

Render free режет исходящий SMTP (OSError «Network is unreachable»), поэтому
основной транспорт — Resend по HTTPS. Здесь проверяем маршрутизацию без сети:
httpx.post замоканы.
"""
from __future__ import annotations

import httpx
import pytest

from app import mailer


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("YUMMY_RESEND_KEY", "YUMMY_SMTP_HOST", "YUMMY_SMTP_FROM",
              "YUMMY_SMTP_PORT", "YUMMY_SMTP_USER", "YUMMY_SMTP_PASS"):
        monkeypatch.delenv(k, raising=False)


def test_not_configured_without_from(monkeypatch):
    monkeypatch.setenv("YUMMY_RESEND_KEY", "re_x")
    assert mailer.is_configured() is False  # нет FROM
    assert mailer.send("a@b.c", "s", "b") is False


def test_resend_used_when_configured(monkeypatch):
    monkeypatch.setenv("YUMMY_RESEND_KEY", "re_x")
    monkeypatch.setenv("YUMMY_SMTP_FROM", "Yummy <no-reply@yummy.kz>")
    sent = {}

    def fake_post(url, headers, json, timeout):
        sent["url"] = url
        sent["to"] = json["to"]
        return httpx.Response(200, json={"id": "abc"})

    monkeypatch.setattr(mailer.httpx, "post", fake_post)
    assert mailer.is_configured() is True
    assert mailer.send("u@ex.com", "Код", "1234") is True
    assert sent["url"] == mailer._RESEND_ENDPOINT
    assert sent["to"] == ["u@ex.com"]


def test_resend_failure_returns_false(monkeypatch):
    monkeypatch.setenv("YUMMY_RESEND_KEY", "re_x")
    monkeypatch.setenv("YUMMY_SMTP_FROM", "no-reply@yummy.kz")
    monkeypatch.setattr(mailer.httpx, "post",
                        lambda *a, **k: httpx.Response(422, json={"message": "domain not verified"}))
    assert mailer.send("u@ex.com", "s", "b") is False


def test_resend_falls_back_to_smtp(monkeypatch):
    monkeypatch.setenv("YUMMY_RESEND_KEY", "re_x")
    monkeypatch.setenv("YUMMY_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("YUMMY_SMTP_FROM", "no-reply@yummy.kz")
    monkeypatch.setattr(mailer.httpx, "post",
                        lambda *a, **k: httpx.Response(500))
    called = {}
    monkeypatch.setattr(mailer, "_send_smtp",
                        lambda to, s, b: called.setdefault("hit", True) or True)
    assert mailer.send("u@ex.com", "s", "b") is True
    assert called.get("hit") is True
