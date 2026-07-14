"""Admin MFA: encrypted seed, TOTP/recovery replay protection and JWT assurance."""
from __future__ import annotations

import time

import pytest
from cryptography.exceptions import InvalidTag

import app.accounts as A
from app.accounts import Accounts, decrypt_mfa_secret, encrypt_mfa_secret, totp_code
from app.db import Store
from app.seed import seed


def test_aes_gcm_mfa_secret_roundtrip_and_aad_binding():
    encrypted = encrypt_mfa_secret("JBSWY3DPEHPK3PXP", "u1")
    assert encrypted.startswith("v1:") and "JBSWY3DPEHPK3PXP" not in encrypted
    assert decrypt_mfa_secret(encrypted, "u1") == "JBSWY3DPEHPK3PXP"
    with pytest.raises(InvalidTag):
        decrypt_mfa_secret(encrypted, "other-user")


def test_rfc6238_sha1_vector_truncated_to_six_digits():
    # RFC 6238 timestamp 59: SHA1 result 94287082; 6-digit authenticators use 287082.
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"
    assert totp_code(secret, 59 // 30) == "287082"


def test_totp_and_recovery_codes_are_one_time(tmp_path):
    accounts = Accounts(tmp_path / "mfa.db")
    uid = accounts.create("admin@example.com", A.hash_password("Secret123"), "admin")
    setup = accounts.configure_mfa(uid, "admin@example.com")
    row = accounts.by_id(uid)
    assert row["mfa_enabled"] == 1
    assert row["mfa_secret"].startswith("v1:")
    assert setup["secret"] not in row["mfa_secret"]
    with accounts._conn() as conn:
        stored = [r[0] for r in conn.execute(
            "SELECT code_hash FROM mfa_recovery_codes WHERE user_id=?", (uid,)
        )]
    assert len(stored) == 10 and all(code not in stored for code in setup["recovery_codes"])

    now = 1_800_000_000
    code = totp_code(setup["secret"], now // 30)
    assert accounts.consume_mfa(uid, code, now=now) == "totp"
    assert accounts.consume_mfa(uid, code, now=now) is None  # replay blocked

    recovery = setup["recovery_codes"][0]
    assert accounts.consume_mfa(uid, recovery, now=now) == "recovery"
    assert accounts.consume_mfa(uid, recovery, now=now) is None


@pytest.fixture
def client(tmp_path, monkeypatch):
    pytest.importorskip("httpx")
    import app.main as main_mod
    from fastapi.testclient import TestClient

    accounts = Accounts(tmp_path / "accounts.db")
    store = Store(tmp_path / "store.db")
    seed(store)
    monkeypatch.setattr(A, "accounts", accounts)
    monkeypatch.setattr(main_mod, "store", store)
    A._auth_hits.clear()
    A._jail.clear()
    main_mod._rate_hits.clear()
    main_mod._ai_hits.clear()
    return TestClient(main_mod.app), accounts


def test_admin_login_requires_mfa_and_refresh_preserves_assurance(client):
    c, accounts = client
    uid = accounts.create("admin@example.com", A.hash_password("Secret123"), "admin")
    setup = accounts.configure_mfa(uid, "admin@example.com")

    missing = c.post("/auth/login", json={
        "email": "admin@example.com", "password": "Secret123",
    })
    assert missing.status_code == 401

    code = totp_code(setup["secret"], int(time.time()) // 30)
    logged = c.post("/auth/login", json={
        "email": "admin@example.com", "password": "Secret123", "mfa_code": code,
    })
    assert logged.status_code == 200
    body = logged.json()
    assert "auth_methods" not in body["user"] and "mfa_enabled" not in body["user"]
    assert "mfa" in A.decode_token(body["access_token"])["amr"]
    admin_headers = {"Authorization": f"Bearer {body['access_token']}"}
    assert c.get("/admin/stats", headers=admin_headers).status_code == 200
    database = c.get("/admin/system/database", headers=admin_headers)
    assert database.status_code == 200
    assert database.json()["backend"] == "sqlite" and "url" not in str(database.json()).lower()

    refreshed = c.post("/auth/refresh", json={"refresh_token": body["refresh_token"]})
    assert refreshed.status_code == 200
    assert "mfa" in A.decode_token(refreshed.json()["access_token"])["amr"]

    recovery = setup["recovery_codes"][0]
    recovered = c.post("/auth/login", json={
        "email": "admin@example.com", "password": "Secret123", "mfa_code": recovery,
    })
    assert recovered.status_code == 200
    replay = c.post("/auth/login", json={
        "email": "admin@example.com", "password": "Secret123", "mfa_code": recovery,
    })
    assert replay.status_code == 401


def test_admin_token_without_mfa_claim_is_rejected(client):
    c, accounts = client
    uid = accounts.create("legacy-admin@example.com", A.hash_password("Secret123"), "admin")
    login = c.post("/auth/login", json={
        "email": "legacy-admin@example.com", "password": "Secret123",
    })
    assert login.status_code == 403 and "MFA" in login.json()["detail"]
    token = A.create_token(uid, "admin")
    denied = c.get("/admin/stats", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 403 and "MFA" in denied.json()["detail"]
