"""DB-API compatibility layer: SQLite dev/tests and pooled PostgreSQL production."""
from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
from pathlib import Path

from psycopg_pool import ConnectionPool

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
_POOL_MIN = max(1, min(int(os.getenv("YUMMY_DB_POOL_MIN", "1")), 20))
_POOL_MAX = max(_POOL_MIN, min(int(os.getenv("YUMMY_DB_POOL_MAX", "10")), 100))
_POOL_TIMEOUT = max(1.0, min(float(os.getenv("YUMMY_DB_POOL_TIMEOUT", "5")), 30.0))
_STATEMENT_TIMEOUT_MS = max(500, min(int(os.getenv("YUMMY_DB_STATEMENT_TIMEOUT_MS", "5000")), 60_000))
_LOCK_TIMEOUT_MS = max(100, min(int(os.getenv("YUMMY_DB_LOCK_TIMEOUT_MS", "2000")), 30_000))
_IDLE_TX_TIMEOUT_MS = max(1_000, min(int(os.getenv("YUMMY_DB_IDLE_TX_TIMEOUT_MS", "10000")), 120_000))
_POOLS: dict[str, ConnectionPool] = {}
_POOLS_LOCK = threading.Lock()


class CompatRow(dict):
    def __getitem__(self, key):
        if isinstance(key, int):
            return list(self.values())[key]
        return super().__getitem__(key)


def _row_factory(cursor):
    columns = [column.name for column in cursor.description]

    def make_row(values):
        return CompatRow(zip(columns, values))

    return make_row


def _pg_sql(sql: str) -> str:
    return sql.replace("?", "%s")


def _pool_for(url: str) -> ConnectionPool:
    with _POOLS_LOCK:
        pool = _POOLS.get(url)
        if pool is None:
            name = "yummy-" + hashlib.sha256(url.encode()).hexdigest()[:10]
            pool = ConnectionPool(
                conninfo=url, min_size=_POOL_MIN, max_size=_POOL_MAX,
                timeout=_POOL_TIMEOUT, open=False, name=name,
                kwargs={
                    "row_factory": _row_factory,
                    "application_name": "yummy-api",
                    "options": (
                        f"-c statement_timeout={_STATEMENT_TIMEOUT_MS} "
                        f"-c lock_timeout={_LOCK_TIMEOUT_MS} "
                        f"-c idle_in_transaction_session_timeout={_IDLE_TX_TIMEOUT_MS}"
                    ),
                },
            )
            _POOLS[url] = pool
        return pool


def close_all_pools() -> None:
    with _POOLS_LOCK:
        pools = list(_POOLS.values())
        _POOLS.clear()
    for pool in pools:
        pool.close()


class PostgresConnection:
    """Context manager returning a pooled transaction-scoped connection."""

    def __init__(self, pool: ConnectionPool):
        self.pool = pool
        self.raw = None
        self._context = None

    def __enter__(self):
        if self.pool.closed:
            # Lazy opening lets Alembic run before application repositories connect.
            self.pool.open(wait=True, timeout=_POOL_TIMEOUT)
        self._context = self.pool.connection(timeout=_POOL_TIMEOUT)
        self.raw = self._context.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        # psycopg connection context commits on success, rolls back on exception,
        # then psycopg_pool returns the clean connection to the shared pool.
        return self._context.__exit__(exc_type, exc, tb)

    def execute(self, sql: str, params=()):
        return self.raw.execute(_pg_sql(sql), params)

    def executemany(self, sql: str, params_seq):
        return self.raw.cursor().executemany(_pg_sql(sql), params_seq)

    def executescript(self, sql: str):
        cursor = self.raw.cursor()
        for statement in (part.strip() for part in sql.split(";")):
            if statement:
                cursor.execute(statement)
        return cursor


class Database:
    def __init__(self, path: Path, database_url: str | None = None, *, use_env: bool = True):
        self.path = Path(path)
        self.url = database_url if database_url is not None else (DATABASE_URL if use_env else "")
        self.is_postgres = self.url.startswith(("postgresql://", "postgres://"))
        self.pool = _pool_for(self.url) if self.is_postgres else None
        if not self.is_postgres:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        if self.is_postgres:
            return PostgresConnection(self.pool)
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection

    def pool_stats(self) -> dict:
        return self.pool.get_stats() if self.pool else {}
