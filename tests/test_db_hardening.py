"""Продакшен-настройки SQLite: WAL, busy_timeout, foreign keys, индексы, бэкап."""
from __future__ import annotations

import sqlite3

from app.db import Store


def test_wal_and_pragmas(tmp_path):
    s = Store(path=tmp_path / "t.db")
    with s._conn() as c:
        assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
        assert c.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert c.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_indexes_created(tmp_path):
    s = Store(path=tmp_path / "t.db")
    with s._conn() as c:
        names = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    for ix in ("ix_boxes_partner", "ix_boxes_status", "ix_orders_partner",
               "ix_orders_user", "ix_orders_status", "ux_partners_owner"):
        assert ix in names, f"нет индекса {ix}"


def test_store_migrates_legacy_partner_schema(tmp_path):
    path = tmp_path / "legacy-store.db"
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE partners(id TEXT PRIMARY KEY,name TEXT,district TEXT,address TEXT,"
            "rating REAL,lat REAL,lng REAL)"
        )
    store = Store(path=path)
    with store._conn() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(partners)")}
    assert "owner_user_id" in columns


def test_db_path_env(tmp_path, monkeypatch):
    """YUMMY_DB_PATH указывает файл БД (persistent-диск на хостинге)."""
    import importlib

    import app.db as dbmod
    monkeypatch.setenv("YUMMY_DB_PATH", str(tmp_path / "sub" / "custom.db"))
    importlib.reload(dbmod)
    dbmod.Store()  # каталог создаётся сам
    assert (tmp_path / "sub" / "custom.db").exists()
    monkeypatch.delenv("YUMMY_DB_PATH")
    importlib.reload(dbmod)  # вернуть модулю дефолтный путь для остальных тестов


def test_backup_tool(tmp_path, monkeypatch):
    src = tmp_path / "live.db"
    Store(path=src)  # создаёт схему
    monkeypatch.setenv("YUMMY_DB_PATH", str(src))

    import importlib

    import tools.backup_db as bk
    importlib.reload(bk)
    monkeypatch.setattr(bk, "DST_DIR", tmp_path / "backups")
    assert bk.main() == 0
    files = list((tmp_path / "backups").glob("yummy-*.db"))
    assert len(files) == 1 and files[0].stat().st_size > 0
    # бэкап — валидная sqlite-БД со схемой
    with sqlite3.connect(files[0]) as c:
        tables = {r[0] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"partners", "boxes", "orders"} <= tables
