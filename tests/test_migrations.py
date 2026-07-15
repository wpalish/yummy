"""Alembic schema and DB compatibility adapter smoke tests."""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from app.database import CompatRow, Database, _pg_sql, close_all_pools

ROOT = Path(__file__).resolve().parent.parent


def test_placeholder_translation_and_compat_row():
    assert _pg_sql("SELECT * FROM users WHERE email=? AND id=?") == (
        "SELECT * FROM users WHERE email=%s AND id=%s"
    )
    row = CompatRow([("id", "u1"), ("email", "a@example.com")])
    assert row[0] == row["id"] == "u1" and dict(row)["email"] == "a@example.com"


def test_postgres_databases_share_a_lazy_pool():
    url = "postgresql://user:pass@localhost/yummy"
    first = Database(Path("ignored.db"), database_url=url)
    second = Database(Path("ignored2.db"), database_url=url)
    assert first.is_postgres and first.pool is second.pool and first.pool.closed
    close_all_pools()


def test_explicit_path_keeps_sqlite_even_if_database_url_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://ignored")
    db = Database(tmp_path / "test.db", use_env=False)
    assert db.is_postgres is False
    with db.connect() as connection:
        assert connection.execute("SELECT 1").fetchone()[0] == 1


def test_initial_migration_applies_to_fresh_sqlite(tmp_path):
    path = tmp_path / "alembic.db"
    env = os.environ | {"DATABASE_URL": f"sqlite:///{path}"}
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"),
         "upgrade", "head"], cwd=ROOT, env=env, check=True, capture_output=True,
    )
    with sqlite3.connect(path) as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        version = connection.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    assert {"users", "partners", "boxes", "orders", "reviews", "refund_requests",
            "refresh_tokens", "action_tokens", "mfa_recovery_codes", "payments",
            "stripe_events"} <= tables
    assert version == "20260714_0002"


def test_postgresql_offline_migration_compiles():
    env = os.environ | {
        "DATABASE_URL": "postgresql+psycopg://user:pass@localhost/yummy"
    }
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"),
         "upgrade", "head", "--sql"], cwd=ROOT, env=env, check=True,
        capture_output=True, text=True,
    )
    assert "CREATE TABLE users" in result.stdout
    assert "CREATE TABLE refund_requests" in result.stdout
    assert "CREATE TABLE payments" in result.stdout
    assert "CREATE TABLE stripe_events" in result.stdout
    assert "CREATE UNIQUE INDEX ux_users_partner" in result.stdout
