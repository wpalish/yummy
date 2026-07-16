"""Двухдрайверный слой БД: Postgres (Supabase) при DATABASE_URL, иначе SQLite.

Цель — переносимость без переписывания вызовов. Store/Accounts продолжают писать
SQL с `?`-плейсхолдерами и `INSERT OR IGNORE`; адаптер транслирует их в диалект
Postgres на лету. Без DATABASE_URL — прежний SQLite (тесты/локаль), нулевой риск.

Go-live: выставить DATABASE_URL (Supabase Session pooler :5432) на бэкенде →
приложение само создаёт схему и работает на Postgres. Откат — убрать переменную.
"""
from __future__ import annotations

import os
import re
import threading
from contextlib import contextmanager
from pathlib import Path

_URL = os.getenv("DATABASE_URL", "").strip()
POSTGRES = bool(_URL)

_SQLITE_PATH = Path(os.getenv("YUMMY_DB_PATH", str(Path(__file__).parent.parent / "spasibox.db")))

# Один процессный лок: сериализует запись, чего достаточно для пилотной нагрузки
# (и для SQLite, и для Postgres). Пул PG даёт параллельные соединения под чтение.
lock = threading.RLock()

_pool = None
if POSTGRES:  # ленивая инициализация зависимостей только когда реально нужен PG
    import psycopg  # noqa: F401
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool

    _SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)  # no-op, симметрия
    _pool = ConnectionPool(_URL, min_size=1, max_size=int(os.getenv("YUMMY_DB_POOL_MAX", "5")),
                           kwargs={"row_factory": dict_row}, open=True)

_IGNORE_RE = re.compile(r"INSERT\s+OR\s+IGNORE\s+INTO", re.IGNORECASE)


def _to_pg(sql: str) -> str | None:
    """Транслировать SQLite-SQL в Postgres. None — если стейтмент надо пропустить."""
    if sql.lstrip().upper().startswith("PRAGMA"):
        return None                       # PRAGMA — только SQLite
    sql = sql.replace("?", "%s")
    if _IGNORE_RE.search(sql):
        sql = _IGNORE_RE.sub("INSERT INTO", sql)
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    return sql


class _PgConn:
    """Обёртка psycopg-соединения под интерфейс sqlite3.Connection (execute/
    executescript/контекст-менеджер), чтобы вызовы Store/Accounts не менялись."""

    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=()):
        pg = _to_pg(sql)
        if pg is None:
            return _Empty()
        cur = self._raw.cursor()
        cur.execute(pg, params)
        return cur                        # psycopg cursor: fetchone/fetchall/rowcount

    def executescript(self, script: str):
        for stmt in script.split(";"):
            if stmt.strip():
                self.execute(stmt)


class _Empty:
    """Заглушка для пропущенных стейтментов (PRAGMA на PG)."""
    def fetchone(self): return None
    def fetchall(self): return []
    rowcount = 0


@contextmanager
def connection():
    """with database.connection() as c: c.execute(...) — коммит на выходе."""
    if POSTGRES:
        raw = _pool.getconn()
        try:
            yield _PgConn(raw)
            raw.commit()
        except Exception:
            raw.rollback()
            raise
        finally:
            _pool.putconn(raw)
    else:
        import sqlite3
        c = sqlite3.connect(str(_SQLITE_PATH), timeout=5.0)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000")
        c.execute("PRAGMA foreign_keys=ON")
        try:
            with c:                       # авто-commit/rollback
                yield c
        finally:
            c.close()
