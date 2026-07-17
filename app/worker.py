"""ARQ worker for durable periodic operational tasks."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone

from arq import cron
from arq.connections import RedisSettings

from .accounts import Accounts, decrypt_mfa_secret
from .db import Store
from .email_delivery import send_outbox_email
from .payments import PaymentUnavailable, gateway, payment_mode


async def startup(ctx):
    ctx["store"] = Store()
    ctx["accounts"] = Accounts()


async def heartbeat(ctx):
    await ctx["redis"].set("yummy:worker:heartbeat", datetime.now(timezone.utc).isoformat(), ex=90)
    return 1


async def expire_reservations(ctx):
    count = await asyncio.to_thread(ctx["store"].expire_payment_reservations)
    if count:
        from .observability import RESERVATION_EXPIRY
        RESERVATION_EXPIRY.inc(count)
    return count


async def cleanup_security_data(ctx):
    return await asyncio.to_thread(ctx["accounts"].cleanup_expired_security_data)


async def reconcile_payments(ctx):
    if payment_mode() != "stripe":
        return 0
    pending = await asyncio.to_thread(ctx["store"].pending_payments, 100)
    processed = 0
    for payment in pending:
        try:
            session = await asyncio.to_thread(gateway.retrieve_checkout, payment["checkout_session_id"])
        except PaymentUnavailable:
            continue
        status = session.get("payment_status")
        if status == "paid":
            event_type = "checkout.session.completed"
        elif session.get("status") == "expired":
            event_type = "checkout.session.expired"
        else:
            continue
        event = {
            "id": f"reconcile:{payment['checkout_session_id']}:{status}",
            "type": event_type,
            "data": {"object": session},
        }
        payload_hash = hashlib.sha256(json.dumps(event, sort_keys=True).encode()).hexdigest()
        await asyncio.to_thread(ctx["store"].process_stripe_event, event, payload_hash)
        processed += 1
    return processed


async def deliver_notifications(ctx):
    rows = await asyncio.to_thread(ctx["store"].due_notifications, 50)
    delivered = 0
    for row in rows:
        try:
            payload = json.loads(decrypt_mfa_secret(row["payload"], row["id"]))
            success = await asyncio.to_thread(
                send_outbox_email, row["recipient_email"],
                payload.get("subject", "Yummy"), payload.get("text", ""),
            )
        except Exception as exc:
            await asyncio.to_thread(ctx["store"].finish_notification, row["id"], False,
                                    type(exc).__name__)
            continue
        await asyncio.to_thread(ctx["store"].finish_notification, row["id"], success,
                                "delivery failed" if not success else "")
        delivered += int(success)
    return delivered


async def generate_commission_invoices(ctx):
    now = datetime.now(timezone.utc)
    first_this_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
    period_to = first_this_month
    previous_day = period_to - timedelta(days=1)
    period_from = datetime(previous_day.year, previous_day.month, 1, tzinfo=timezone.utc)
    due_at = period_to + timedelta(days=10)
    return await asyncio.to_thread(
        ctx["store"].generate_commission_invoices,
        period_from.isoformat(), period_to.isoformat(), due_at.isoformat(),
    )


def redis_settings() -> RedisSettings:
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return RedisSettings.from_dsn(url)


class WorkerSettings:
    redis_settings = redis_settings()
    on_startup = startup
    functions = [heartbeat, expire_reservations, cleanup_security_data,
                 reconcile_payments, deliver_notifications, generate_commission_invoices]
    cron_jobs = [
        cron(heartbeat, second={0, 30}),
        cron(expire_reservations, minute=None, second=5),
        cron(reconcile_payments, minute=None, second=20),
        cron(deliver_notifications, minute=None, second=40),
        cron(cleanup_security_data, hour=3, minute=15),
        cron(generate_commission_invoices, day=1, hour=4, minute=0),
    ]
    max_jobs = 10
    job_timeout = 60
    keep_result = 3600
