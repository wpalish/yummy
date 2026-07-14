"""Small DB-API compatibility layer for SQLite (dev/tests) and PostgreSQL.

Repositories keep parameterized SQL with ``?`` placeholders; the adapter converts
those placeholders to psycopg's ``%s``. PostgreSQL schema is owned by Alembic.
"""
from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import psycopg

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


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


class PostgresConnection:
    def __init__(self, url: str):
        self.raw = psycopg.connect(url, row_factory=_row_factory)

    def __enter__(self):
        self.raw.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        return self.raw.__exit__(exc_type, exc, tb)

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
        if not self.is_postgres:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self):
        if self.is_postgres:
            return PostgresConnection(self.url)
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=5000")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA synchronous=NORMAL")
        return connection
