"""Production must never expose demo inventory, payments, reviews or staff access."""
from __future__ import annotations

from pathlib import Path

import pytest


def test_production_rejects_demo_payment_configuration(monkeypatch):
    import app.payments as payments

    monkeypatch.setattr(payments, "_MODE", "demo")
    with pytest.raises(RuntimeError, match="запрещает demo"):
        payments.assert_payment_config(True)
    monkeypatch.setattr(payments, "_MODE", "disabled")
    payments.assert_payment_config(True)


def test_production_blocks_fake_paid_orders_seed_and_static_venues(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main
    import app.payments as payments

    monkeypatch.setattr(main, "_PRODUCTION", True)
    monkeypatch.setattr(payments, "_MODE", "disabled")
    client = TestClient(main.app)
    fake = client.post("/orders", json={
        "box_id": "any-box", "user_name": "User", "user_phone": "+77000",
    })
    assert fake.status_code == 410
    assert client.post("/admin/seed").status_code == 404
    assert client.get("/static/venues.json").status_code == 404
    config = client.get("/config").json()
    assert config == {
        "payment_mode": "disabled", "payments_enabled": False,
        "production": True, "currency": "kzt",
    }


def test_production_frontend_has_explicit_demo_guards():
    html = Path("app/static/index.html").read_text(encoding="utf-8")
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    assert "demo-only" in html
    assert "applyEnvironmentVisibility" in js
    assert "Локальные демо-брони отключены" in js
    assert "Подтверждённых отзывов пока нет" in js
    assert "Демо-PIN" not in html and "Демо-PIN" not in js
