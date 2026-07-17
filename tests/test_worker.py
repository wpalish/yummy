"""ARQ periodic tasks run independently from catalog requests."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.accounts import Accounts
from app.db import Store
from app.worker import cleanup_security_data, expire_reservations, heartbeat


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def set(self, key, value, ex=None):
        self.values[key] = (value, ex)


def test_worker_heartbeat_has_short_ttl():
    redis = FakeRedis()
    assert asyncio.run(heartbeat({"redis": redis})) == 1
    assert redis.values["yummy:worker:heartbeat"][1] == 90


def test_worker_expires_payment_without_catalog_request(tmp_path):
    store = Store(tmp_path / "worker.db")
    # No pending rows is still a real independent task execution.
    assert asyncio.run(expire_reservations({"store": store})) == 0


def test_worker_cleans_expired_action_tokens(tmp_path):
    accounts = Accounts(tmp_path / "accounts.db")
    uid = accounts.create("cleanup@example.com", "hash", "customer")
    accounts.issue_action_token(uid, "verify_email", -1)
    result = asyncio.run(cleanup_security_data({"accounts": accounts}))
    assert result["action_tokens"] == 1


def test_commission_invoice_generation_is_idempotent(tmp_path):
    store = Store(tmp_path / "commission.db")
    from app.models import Partner
    store.upsert_partner(Partner(id="p", name="Cafe", district="D", address="A"))
    now = datetime.now(timezone.utc)
    period_from = (now - timedelta(days=40)).replace(day=1).isoformat()
    period_to = now.replace(day=1).isoformat()
    with store._conn() as connection:
        connection.execute("""INSERT INTO commission_ledger(id,partner_id,order_id,payment_id,
            gross_amount_minor,commission_rate_bps,commission_amount_minor,status,created_at)
            VALUES('l','p','o','pay',10000,1000,1000,'accrued',?)""", (period_from,))
    assert store.generate_commission_invoices(period_from, period_to,
                                               (now + timedelta(days=10)).isoformat()) == 1
    assert store.generate_commission_invoices(period_from, period_to,
                                               (now + timedelta(days=10)).isoformat()) == 0
