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
    assert "form-action 'self'" in h["content-security-policy"]
    script_policy = h["content-security-policy"].split("script-src ", 1)[1].split(";", 1)[0]
    assert "'unsafe-inline'" not in script_policy
    assert "script-src-attr 'none'" in h["content-security-policy"]
    assert h["cross-origin-opener-policy"] == "same-origin"
    assert h["cross-origin-resource-policy"] == "cross-origin"
    assert h["cache-control"] == "no-store"
    assert len(h["x-request-id"]) == 32


def test_csp_allows_camera_for_scanner():
    """QR-сканер баристы требует камеру — она должна быть разрешена (self)."""
    r = _client().get("/health")
    assert "camera=(self)" in r.headers["permissions-policy"]


def test_frontend_has_no_inline_handlers_or_browser_tokens():
    import base64
    import hashlib
    import re
    from pathlib import Path

    html = Path("app/static/index.html").read_text(encoding="utf-8")
    js = Path("app/static/app.js").read_text(encoding="utf-8")
    assert 'onclick="' not in html and 'onclick="' not in js
    assert "access_token" not in js and "refresh_token" not in js
    assert 'Authorization' not in js
    assert "/session/login" in js and "X-CSRF-Token" in js

    json_ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', html).group(1)
    digest = base64.b64encode(hashlib.sha256(json_ld.encode()).digest()).decode()
    csp = _client().get("/").headers["content-security-policy"]
    assert f"'sha256-{digest}'" in csp
    integrity = re.search(r'<script src="[^"]*leaflet[^"]*" integrity="([^"]+)"', html).group(1)
    assert f"'{integrity}'" in csp


def test_every_csp_safe_data_action_has_a_dispatch_case():
    import re
    from pathlib import Path

    source = (Path("app/static/index.html").read_text(encoding="utf-8")
              + Path("app/static/app.js").read_text(encoding="utf-8"))
    actions = set(re.findall(r'data-action=[\\"]+([^\\"`]+)', source))
    cases = set(re.findall(r'case "([^"]+)"', source))
    assert actions and actions == cases


def test_root_scope_pwa_assets_are_served():
    client = _client()
    manifest = client.get("/manifest.json")
    worker = client.get("/sw.js")
    assert manifest.status_code == 200 and manifest.json()["scope"] == "/"
    assert worker.status_code == 200
    assert worker.headers["service-worker-allowed"] == "/"


def test_liveness_does_not_depend_on_database_but_readiness_does(monkeypatch):
    import app.main as main_mod

    client = _client()
    monkeypatch.setattr(main_mod.store, "ping", lambda: (_ for _ in ()).throw(RuntimeError("down")))
    assert client.get("/live").status_code == 200
    readiness = client.get("/health")
    assert readiness.status_code == 503 and readiness.json()["detail"] == "database unavailable"


def test_host_header_allowlist_rejects_unknown_host():
    from fastapi.testclient import TestClient
    from app.main import app

    response = TestClient(app, base_url="http://evil.example").get("/health")
    assert response.status_code == 400


def test_request_body_size_limit():
    response = _client().post(
        "/auth/register",
        content=b"x" * 70_000,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 413


def test_json_api_rejects_wrong_content_type():
    response = _client().post(
        "/auth/login",
        content="email=a@example.com&password=Secret123",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415


def test_cors_preflight_allows_only_configured_origin_and_methods():
    allowed = _client().options("/me", headers={
        "Origin": "https://wpalish.github.io",
        "Access-Control-Request-Method": "DELETE",
        "Access-Control-Request-Headers": "Authorization",
    })
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://wpalish.github.io"
    assert "access-control-allow-credentials" not in allowed.headers
    assert "DELETE" in allowed.headers["access-control-allow-methods"]
    assert "X-CSRF-Token" in allowed.headers["access-control-allow-headers"]

    denied = _client().options("/me", headers={
        "Origin": "https://evil.example",
        "Access-Control-Request-Method": "DELETE",
    })
    assert "access-control-allow-origin" not in denied.headers


def test_production_requires_postgresql(monkeypatch):
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "_PRODUCTION", True)
    monkeypatch.setattr(main_mod.store._database, "is_postgres", False)
    with pytest.raises(RuntimeError, match="PostgreSQL DATABASE_URL"):
        main_mod._assert_database_config()
    monkeypatch.setattr(main_mod.store._database, "is_postgres", True)
    main_mod._assert_database_config()


def test_production_edge_config_fails_closed(monkeypatch):
    import app.main as main_mod

    monkeypatch.setattr(main_mod, "_PRODUCTION", True)
    monkeypatch.delenv("YUMMY_ALLOWED_HOSTS", raising=False)
    with pytest.raises(RuntimeError, match="YUMMY_ALLOWED_HOSTS"):
        main_mod._assert_edge_config()

    monkeypatch.setenv("YUMMY_ALLOWED_HOSTS", "api.example.com")
    monkeypatch.setattr(main_mod, "_ALLOWED_HOSTS", ["api.example.com"])
    monkeypatch.setattr(main_mod, "_CORS", ["https://app.example.com"])
    main_mod._assert_edge_config()
