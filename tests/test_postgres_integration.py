"""Optional real-PostgreSQL integration; CI enables via TEST_DATABASE_URL."""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.accounts import Accounts, hash_password
from app.db import Store
from app.models import BoxCreate, Partner

URL = os.getenv("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not configured")
ROOT = Path(__file__).resolve().parent.parent


def test_postgres_migration_and_transactional_order_flow():
    env = os.environ | {"DATABASE_URL": URL}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                   cwd=ROOT, env=env, check=True, capture_output=True)
    accounts = Accounts(database_url=URL)
    store = Store(database_url=URL)
    with accounts._conn() as connection:
        connection.executescript(
            "DELETE FROM mfa_recovery_codes; DELETE FROM action_tokens; "
            "DELETE FROM refresh_tokens; DELETE FROM users;"
        )
    store.reset()

    uid = accounts.create("pg@example.com", hash_password("Secret123"), "customer")
    assert accounts.by_id(uid)["email"] == "pg@example.com"
    store.upsert_partner(Partner(id="pg-partner", name="PG Cafe", district="Нура",
                                 address="ул. 1"))
    now = datetime.now(timezone.utc)
    box = store.create_box("pg-box", BoxCreate(
        partner_id="pg-partner", category="bakery", title="PG box", price=900,
        value_est=2000, qty=1, pickup_from=now.isoformat(),
        pickup_to=(now + timedelta(hours=2)).isoformat(),
    ))
    order = store.create_order("pg-order", "YM-PG001-PG001", box, "User", "+77000", uid)
    assert order and store.box("pg-box").qty_left == 0
    assert store.create_order("pg-order-2", "YM-PG002-PG002", box, "User", "+77000", uid) is None
