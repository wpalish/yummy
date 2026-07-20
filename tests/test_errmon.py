"""№6 аудита: необработанные 500 репортятся (Sentry/TG), а не тонут в логах."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import errmon
from app import main as main_mod


def test_dedup_window(monkeypatch):
    errmon._last_sent.clear()
    calls = []
    monkeypatch.setattr(errmon, "_sentry_send", lambda e, p: calls.append(p) or True)
    monkeypatch.setattr(errmon, "_telegram_send", lambda e, p: False)
    exc = ValueError("boom")
    errmon.report(exc, "/x")
    errmon.report(exc, "/x")            # тот же тип+путь в окне — не шлётся
    errmon.report(exc, "/y")            # другой путь — шлётся
    assert calls == ["/x", "/y"]


def test_noop_without_config(monkeypatch):
    """Без SENTRY_DSN и TG-чата report не делает сетевых вызовов и не падает."""
    errmon._last_sent.clear()
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("YUMMY_ORDERS_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    errmon.report(RuntimeError("тихо"), "/silent")   # не бросает


def test_unhandled_500_reported(monkeypatch, tmp_path):
    """Middleware зовёт errmon.report на необработанном исключении."""
    errmon._last_sent.clear()
    reported = []
    monkeypatch.setattr(errmon, "report", lambda exc, path="?": reported.append((type(exc).__name__, path)))

    @main_mod.app.get("/__boom_test")
    def _boom():
        raise RuntimeError("специально")

    try:
        c = TestClient(main_mod.app, raise_server_exceptions=False)
        r = c.get("/__boom_test")
        assert r.status_code == 500
        assert reported == [("RuntimeError", "/__boom_test")]
    finally:
        main_mod.app.router.routes = [
            rt for rt in main_mod.app.router.routes
            if getattr(rt, "path", "") != "/__boom_test"]
