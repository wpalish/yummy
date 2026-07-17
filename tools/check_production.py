"""Read-only production readiness checks without printing secrets/DSNs."""
from __future__ import annotations

import os

import psycopg
from redis import Redis

EXPECTED_REVISION = "20260714_0004"
EXPECTED_TABLES = {
    "users", "partners", "boxes", "orders", "payments", "stripe_events",
    "refund_requests", "staff_invitations", "partner_payment_accounts",
    "commission_rules", "commission_ledger", "commission_invoices",
}


def main() -> int:
    database_url = os.getenv("DATABASE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")
    required = ["YUMMY_SECRET_KEY", "YUMMY_DATA_KEY", "YUMMY_RATE_LIMIT_KEY",
                "YUMMY_PUBLIC_URL", "YUMMY_ALLOWED_HOSTS"]
    missing = [name for name in required if not os.getenv(name)]
    if not database_url or not redis_url or missing:
        print("FAIL missing configuration:", ", ".join((["DATABASE_URL"] if not database_url else []) + (["REDIS_URL"] if not redis_url else []) + missing))
        return 2
    try:
        with psycopg.connect(database_url, connect_timeout=5) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT version_num FROM alembic_version")
                revision = cursor.fetchone()[0]
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
                tables = {row[0] for row in cursor.fetchall()}
                cursor.execute("SHOW statement_timeout")
                statement_timeout = cursor.fetchone()[0]
    except Exception as exc:
        print("FAIL database:", type(exc).__name__)
        return 3
    if revision != EXPECTED_REVISION or EXPECTED_TABLES - tables:
        print("FAIL schema revision/tables")
        return 4
    try:
        redis = Redis.from_url(redis_url, socket_connect_timeout=3)
        if not redis.ping():
            raise RuntimeError("ping false")
        if os.getenv("YUMMY_REQUIRE_WORKER", "0") in {"1", "true", "yes"}:
            if not redis.exists("yummy:worker:heartbeat"):
                raise RuntimeError("worker heartbeat missing")
    except Exception as exc:
        print("FAIL redis:", type(exc).__name__)
        return 5
    print(f"OK database revision={revision} tables={len(tables)} statement_timeout={statement_timeout}")
    print("OK redis")
    print("OK secrets present (values not displayed)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
