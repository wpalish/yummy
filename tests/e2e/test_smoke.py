"""E2E-smoke (Playwright): критические пользовательские флоу живьём в браузере.

Бэкенд-тесты не видят фронт (2600 строк JS): сегодняшний «дубль const убил весь
сайт» ловится только так. Запуск локально:
    .venv/bin/python -m pytest tests/e2e -q
Без установленного playwright/chromium — skip, обычный прогон не страдает.
Сервер поднимается сам на :8031 в открытом демо-режиме (свежая БД + демо-сид).
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

pw = pytest.importorskip("playwright.sync_api", reason="playwright не установлен")

ROOT = Path(__file__).parent.parent.parent
PORT = 8031
BASE = f"http://127.0.0.1:{PORT}"


def _wait_port(port: int, timeout: float = 20.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.2)
    return False


@pytest.fixture(scope="module")
def server(tmp_path_factory):
    db = tmp_path_factory.mktemp("e2e") / "e2e.db"
    env = {**os.environ, "YUMMY_ENFORCE_AUTH": "0", "YUMMY_DB_PATH": str(db),
           "YUMMY_PAYMENT_MODE": "demo", "TELEGRAM_BOT_TOKEN": "", "ANTHROPIC_API_KEY": ""}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(PORT)],
        cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert _wait_port(PORT), "uvicorn не поднялся"
    yield BASE
    proc.terminate()
    proc.wait(timeout=10)


@pytest.fixture(scope="module")
def page(server):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception:
            pytest.skip("chromium не установлен (playwright install chromium)")
        pg = browser.new_page()
        yield pg
        browser.close()


def _fresh(page, server):
    page.goto(server)
    # гостевой вход, чтобы уйти с лендинга в каталог
    page.evaluate("localStorage.setItem('ym_account',"
                  "JSON.stringify({role:'guest',name:'Гость',createdAt:Date.now()}))")
    page.goto(server)
    page.wait_for_selector("#view-store:not(.hidden)", timeout=10_000)


def test_catalog_renders_boxes(page, server):
    """Витрина открывается, демо-каталог показывает карточки боксов."""
    _fresh(page, server)
    page.wait_for_selector(".boxc", timeout=10_000)
    assert page.locator(".boxc").count() >= 3
    assert "Астан" in page.locator("#view-store h1").first.inner_text()


def test_booking_gives_pickup_code(page, server):
    """Критический флоу покупателя: бокс → бронь → код выдачи YM-XXXX."""
    _fresh(page, server)
    page.wait_for_selector(".boxc", timeout=10_000)
    page.locator(".boxc").first.click()
    page.wait_for_selector("#modal .mc", timeout=5_000)
    page.fill("#oName", "E2E Тест")
    page.fill("#oPhone", "+77010000001")
    page.locator("#payBtn").click()
    code_el = page.wait_for_selector("text=/YM-[A-Z0-9]{4}/", timeout=10_000)
    assert "YM-" in code_el.inner_text()


def test_no_js_errors_on_load(page, server):
    """Страница загружается без единой JS-ошибки в консоли."""
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    _fresh(page, server)
    page.wait_for_timeout(1500)
    assert not errors, f"JS-ошибки на странице: {errors}"
