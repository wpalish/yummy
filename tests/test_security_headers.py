"""Проверка, что бэкенд отдаёт защитные HTTP-заголовки (нужен httpx → в CI)."""
import pytest


def _client():
    pytest.importorskip("httpx")
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


def test_security_headers_present():
    r = _client().get("/health")
    h = r.headers
    assert "content-security-policy" in h
    assert h["x-frame-options"] == "DENY"
    assert h["x-content-type-options"] == "nosniff"
    assert "strict-origin-when-cross-origin" in h["referrer-policy"]
    assert "frame-ancestors 'none'" in h["content-security-policy"]


def test_csp_allows_camera_for_scanner():
    """QR-сканер баристы требует камеру — она должна быть разрешена (self)."""
    r = _client().get("/health")
    assert "camera=(self)" in r.headers["permissions-policy"]
