"""Консистентный бэкап SQLite (официальный backup API — безопасен при живом WAL).

Использование: make backup  → backups/yummy-YYYYmmdd-HHMMSS.db
Хранит последние 14 копий, старые удаляет.
"""
from __future__ import annotations

import os
import sqlite3
import time
from pathlib import Path

KEEP = 14
ROOT = Path(__file__).resolve().parent.parent
SRC = Path(os.getenv("YUMMY_DB_PATH", str(ROOT / "spasibox.db")))
DST_DIR = ROOT / "backups"


def main() -> int:
    if not SRC.exists():
        print(f"БД не найдена: {SRC}")
        return 1
    DST_DIR.mkdir(exist_ok=True)
    dst = DST_DIR / f"yummy-{time.strftime('%Y%m%d-%H%M%S')}.db"
    with sqlite3.connect(SRC) as src, sqlite3.connect(dst) as out:
        src.backup(out)
    print(f"бэкап: {dst} ({dst.stat().st_size} байт)")
    old = sorted(DST_DIR.glob("yummy-*.db"))[:-KEEP]
    for f in old:
        f.unlink()
        print(f"удалён старый: {f.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
