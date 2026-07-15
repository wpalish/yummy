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


def test_request_id_header_present_and_unique():
    c = _client()
    r1 = c.get("/health")
    r2 = c.get("/health")
    assert len(r1.headers["x-request-id"]) == 32
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]  # уникален на запрос


def test_extra_isolation_headers():
    h = _client().get("/health").headers
    assert h["cross-origin-opener-policy"] == "same-origin"
    assert h["cross-origin-resource-policy"] == "cross-origin"
    assert h["x-permitted-cross-domain-policies"] == "none"


def test_body_size_limit_rejects_oversized():
    import app.main as m
    c = _client()
    big = "x" * (m._MAX_BODY + 1)
    r = c.post("/orders/cancel", data=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    assert r.headers["x-request-id"]


def test_normal_body_passes_size_limit():
    # маленькое тело проходит лимит (доходит до бизнес-логики → 409 «не найден»)
    r = _client().post("/orders/cancel", json={"code": "YM-NOPE"})
    assert r.status_code == 409
