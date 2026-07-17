"""Encrypted partner merchant accounts and commission ledger."""
from __future__ import annotations

import pytest

import app.accounts as A
from app.accounts import Accounts
from app.db import Store
from app.models import Partner


@pytest.fixture
def setup(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main

    accounts = Accounts(tmp_path / "accounts.db")
    store = Store(tmp_path / "store.db")
    store.upsert_partner(Partner(id="p-real", name="Real Cafe", district="Нура", address="ул. 1"))
    monkeypatch.setattr(A, "accounts", accounts)
    monkeypatch.setattr(main, "store", store)
    admin_id = accounts.create("admin@example.com", A.hash_password("Secret123"), "admin")
    accounts.configure_mfa(admin_id, "admin@example.com")
    admin = accounts.by_id(admin_id)
    admin_token = A.create_token(admin_id, "admin", ver=admin["token_ver"], mfa_verified=True)
    return TestClient(main.app), store, {"Authorization": f"Bearer {admin_token}"}


def test_credentials_are_encrypted_and_never_returned(setup):
    client, store, admin = setup
    secret = "merchant-super-secret-token"
    response = client.post("/admin/partner-payment-accounts", headers=admin, json={
        "partner_id": "p-real", "provider": "kaspi", "merchant_reference": "merchant-12345678",
        "point_of_service_id": "pos-1", "credentials": secret,
    })
    assert response.status_code == 201
    body = response.json()
    assert secret not in str(body) and body["merchant_reference_masked"].endswith("5678")
    row = store.payment_account("p-real", "kaspi")
    assert row["credentials_encrypted"].startswith("v1:")
    assert secret not in row["credentials_encrypted"]

    active = client.post(
        f"/admin/partner-payment-accounts/{body['id']}/status", headers=admin,
        json={"status": "active", "payments_enabled": True,
              "refunds_enabled": True, "reason": "Тестовый платёж подтверждён"},
    )
    assert active.status_code == 200 and active.json()["payments_enabled"] is True


def test_commission_uses_integer_basis_points_and_is_idempotent(setup):
    client, store, admin = setup
    rule = client.post("/admin/commission-rules", headers=admin, json={
        "partner_id": "p-real", "rate_basis_points": 750,
    })
    assert rule.status_code == 200
    # Minimal authoritative rows for ledger accrual.
    with store._conn() as connection:
        connection.execute("""INSERT INTO boxes(id,partner_id,category,title,price,value_est,
            qty_total,qty_left,pickup_from,pickup_to,description,created_at,status)
            VALUES('b','p-real','sweet','Box',1000,2000,1,0,'x','x','','x','active')""")
        connection.execute("""INSERT INTO orders(id,code,box_id,partner_id,category,price,
            user_name,user_phone,status,pickup_from,pickup_to,created_at,payment_status)
            VALUES('o','YM-TEST1-TEST1','b','p-real','sweet',1000,'U','P','paid','x','x','x','paid')""")
        connection.execute("""INSERT INTO payments(id,order_id,provider,status,currency,amount_minor,
            idempotency_key,reservation_expires_at,created_at,updated_at)
            VALUES('pay','o','stripe','paid','kzt',100000,'idem','x','x','9999')""")
    first = store.accrue_commission("o", "pay")
    second = store.accrue_commission("o", "pay")
    assert first["commission_rate_bps"] == 750
    assert first["commission_amount_minor"] == 7500
    assert second["id"] == first["id"]
