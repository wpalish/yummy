"""Optional real-PostgreSQL integration; CI enables via TEST_DATABASE_URL."""
from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
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
    with store._conn() as connection:
        assert connection.execute("SHOW statement_timeout").fetchone()[0] == "5s"
        assert connection.execute("SHOW lock_timeout").fetchone()[0] == "2s"
        assert connection.execute("SHOW application_name").fetchone()[0] == "yummy-api"
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
    replica_a = Store(database_url=URL)
    replica_b = Store(database_url=URL)

    def buy(replica, order_id, code):
        return replica.create_order(order_id, code, box, "User", "+77000", uid)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(buy, replica_a, "pg-order-a", "YM-PG001-PG001"),
            executor.submit(buy, replica_b, "pg-order-b", "YM-PG002-PG002"),
        ]
    results = [future.result() for future in futures]
    assert sum(result is not None for result in results) == 1
    assert store.box("pg-box").qty_left == 0
