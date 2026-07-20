"""№6 аудита: необработанные 500 репортятся (Sentry/TG), а не тонут в логах."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import errmon
from app import main as main_mod


@pytest.fixture(autouse=True)
def _clean_dedup():
    """Глобальная карта дедупа — общая на процесс: в полном прогоне её пишет
    middleware из других тестов. Чистим до и после, чтобы порядок в CI не влиял."""
    errmon._last_sent.clear()
    yield
    errmon._last_sent.clear()


def test_dedup_first_allows_then_blocks_same_key():
    """Чистая проверка окна: первый ключ пропускается, повтор — нет."""
    assert errmon._dedup("ValueError:/x") is True
    assert errmon._dedup("ValueError:/x") is False    # тот же ключ в окне
    assert errmon._dedup("ValueError:/y") is True      # другой ключ — свежий


def test_report_sends_once_per_key(monkeypatch):
    calls = []
    monkeypatch.setattr(errmon, "_sentry_send", lambda e, p: calls.append(p) or True)
    monkeypatch.setattr(errmon, "_telegram_send", lambda e, p: False)
    exc = ValueError("boom")
    errmon.report(exc, "/x")
    errmon.report(exc, "/x")            # дедуп — второй раз не шлём
    errmon.report(exc, "/y")
    assert calls == ["/x", "/y"]


def test_noop_without_config(monkeypatch):
    """Без SENTRY_DSN и TG-чата report не делает сетевых вызовов и не падает."""
    monkeypatch.delenv("SENTRY_DSN", raising=False)
    monkeypatch.delenv("YUMMY_ORDERS_CHAT_ID", raising=False)
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "")
    errmon.report(RuntimeError("тихо"), "/silent")   # не бросает


def test_unhandled_500_reported(monkeypatch):
    """Middleware зовёт errmon.report на необработанном исключении."""
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
