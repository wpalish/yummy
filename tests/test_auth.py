"""Тесты контроля доступа: партнёрские и админские эндпоинты требуют токен,
витрина магазина остаётся публичной."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_store_endpoints_are_public(client):
    assert client.get("/boxes").status_code == 200
    assert client.get("/districts").status_code == 200
    assert client.get("/health").status_code == 200


def test_admin_fail_closed_without_token_env(client, monkeypatch):
    monkeypatch.delenv("ADMIN_TOKEN", raising=False)
    assert client.get("/admin/stats").status_code == 503
    assert client.get("/admin/orders").status_code == 503
    assert client.post("/admin/refund/o1").status_code == 503


def test_admin_rejects_missing_or_wrong_token(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    assert client.get("/admin/stats").status_code == 401
    assert client.get("/admin/stats", headers={"X-Admin-Token": "nope"}).status_code == 401


def test_admin_accepts_correct_token(client, monkeypatch):
    monkeypatch.setenv("ADMIN_TOKEN", "s3cret")
    r = client.get("/admin/stats", headers={"X-Admin-Token": "s3cret"})
    assert r.status_code == 200


def test_partner_endpoints_require_token(client, monkeypatch):
    monkeypatch.setenv("PARTNER_TOKEN", "ptok")
    assert client.get("/partners/p1/orders").status_code == 401
    assert client.post("/redeem", json={"code": "SB-XXXX"}).status_code == 401
    assert client.post(
        "/boxes",
        json={
            "partner_id": "p1", "category": "sweet", "price": 900, "value_est": 2500,
            "qty": 1, "pickup_from": "2030-01-01T00:00:00+00:00",
            "pickup_to": "2030-01-01T04:00:00+00:00",
        },
    ).status_code == 401


def test_partner_accepts_correct_token(client, monkeypatch):
    monkeypatch.setenv("PARTNER_TOKEN", "ptok")
    r = client.get("/partners/p1/orders", headers={"X-Partner-Token": "ptok"})
    assert r.status_code == 200
