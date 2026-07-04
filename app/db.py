"""SQLite-хранилище MVP: партнёры, боксы, заказы. Локально, без внешних БД."""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .models import Box, Order, Partner

_DB = Path(__file__).parent.parent / "spasibox.db"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_past(iso: str) -> bool:
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return False
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > dt


class Store:
    """Потокобезопасная обёртка над SQLite."""

    def __init__(self, path: Path = _DB) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._init()

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path)
        c.row_factory = sqlite3.Row
        return c

    def _init(self) -> None:
        with self._lock, self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS partners(
                    id TEXT PRIMARY KEY, name TEXT, district TEXT, address TEXT, rating REAL,
                    token TEXT);
                CREATE TABLE IF NOT EXISTS boxes(
                    id TEXT PRIMARY KEY, partner_id TEXT, category TEXT, title TEXT,
                    price INTEGER, value_est INTEGER, qty_total INTEGER, qty_left INTEGER,
                    pickup_from TEXT, pickup_to TEXT, description TEXT, created_at TEXT,
                    status TEXT DEFAULT 'active');
                CREATE TABLE IF NOT EXISTS orders(
                    id TEXT PRIMARY KEY, code TEXT UNIQUE, box_id TEXT, partner_id TEXT,
                    category TEXT, price INTEGER, user_name TEXT, user_phone TEXT,
                    status TEXT, pickup_from TEXT, pickup_to TEXT, created_at TEXT);
                """
            )
            cols = {r["name"] for r in c.execute("PRAGMA table_info(partners)")}
            if "token" not in cols:
                c.execute("ALTER TABLE partners ADD COLUMN token TEXT")

    # ------------------------------------------------------------------ #
    #  Партнёры
    # ------------------------------------------------------------------ #
    def partners(self) -> list[Partner]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM partners ORDER BY name").fetchall()
        return [Partner(**{k: r[k] for k in ("id", "name", "district", "address", "rating")}) for r in rows]

    def _partner_row(self, c: sqlite3.Connection, pid: str) -> sqlite3.Row | None:
        return c.execute("SELECT * FROM partners WHERE id=?", (pid,)).fetchone()

    def upsert_partner(self, p: Partner, token: str | None = None) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO partners(id,name,district,address,rating,token)
                   VALUES(?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                       district=excluded.district, address=excluded.address,
                       rating=excluded.rating,
                       token=COALESCE(excluded.token, partners.token)""",
                (p.id, p.name, p.district, p.address, p.rating, token),
            )

    def partner_by_token(self, token: str) -> str | None:
        """id партнёра по токену доступа (None — неверный токен)."""
        if not token:
            return None
        with self._lock, self._conn() as c:
            r = c.execute("SELECT id FROM partners WHERE token=?", (token,)).fetchone()
        return r["id"] if r else None

    # ------------------------------------------------------------------ #
    #  Боксы
    # ------------------------------------------------------------------ #
    def _box_from_row(self, c: sqlite3.Connection, r: sqlite3.Row) -> Box:
        p = self._partner_row(c, r["partner_id"])
        return Box(
            id=r["id"], partner_id=r["partner_id"],
            partner_name=p["name"] if p else "—",
            district=p["district"] if p else "",
            address=p["address"] if p else "",
            rating=p["rating"] if p else 0.0,
            category=r["category"], title=r["title"], price=r["price"],
            value_est=r["value_est"], qty_total=r["qty_total"], qty_left=r["qty_left"],
            pickup_from=r["pickup_from"], pickup_to=r["pickup_to"],
            description=r["description"], created_at=r["created_at"],
        )

    def create_box(self, box_id: str, data) -> Box:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO boxes(id,partner_id,category,title,price,value_est,
                       qty_total,qty_left,pickup_from,pickup_to,description,created_at,status)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'active')""",
                (box_id, data.partner_id, data.category, data.title, data.price,
                 data.value_est, data.qty, data.qty, data.pickup_from, data.pickup_to,
                 data.description, _now_iso()),
            )
            r = c.execute("SELECT * FROM boxes WHERE id=?", (box_id,)).fetchone()
            return self._box_from_row(c, r)

    def box(self, box_id: str) -> Box | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM boxes WHERE id=?", (box_id,)).fetchone()
            return self._box_from_row(c, r) if r else None

    def boxes_available(self, district: str | None = None) -> list[Box]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM boxes WHERE status='active' AND qty_left>0 "
                "ORDER BY created_at DESC"
            ).fetchall()
            boxes = [self._box_from_row(c, r) for r in rows if not _is_past(r["pickup_to"])]
        if district and district != "all":
            boxes = [b for b in boxes if b.district == district]
        return boxes

    def partner_boxes(self, partner_id: str) -> list[Box]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM boxes WHERE partner_id=? ORDER BY created_at DESC",
                (partner_id,),
            ).fetchall()
            return [self._box_from_row(c, r) for r in rows]

    def close_box(self, box_id: str, partner_id: str) -> bool:
        """Снять бокс с продажи (только свой). Уже оплаченные брони остаются в силе."""
        with self._lock, self._conn() as c:
            cur = c.execute(
                "UPDATE boxes SET status='closed' WHERE id=? AND partner_id=? AND status='active'",
                (box_id, partner_id),
            )
            return cur.rowcount > 0

    def _take_one(self, c: sqlite3.Connection, box_id: str) -> bool:
        """Атомарно уменьшить остаток бокса на 1 (если есть). True — успех."""
        cur = c.execute(
            "UPDATE boxes SET qty_left=qty_left-1 WHERE id=? AND qty_left>0", (box_id,)
        )
        return cur.rowcount > 0

    def _return_one(self, c: sqlite3.Connection, box_id: str) -> None:
        c.execute("UPDATE boxes SET qty_left=qty_left+1 WHERE id=?", (box_id,))

    # ------------------------------------------------------------------ #
    #  Заказы
    # ------------------------------------------------------------------ #
    def _order_from_row(self, c: sqlite3.Connection, r: sqlite3.Row) -> Order:
        p = self._partner_row(c, r["partner_id"])
        status = self._effective_status(r["status"], r["pickup_to"])
        return Order(
            id=r["id"], code=r["code"], box_id=r["box_id"], partner_id=r["partner_id"],
            partner_name=p["name"] if p else "—", address=p["address"] if p else "",
            category=r["category"], price=r["price"], user_name=r["user_name"],
            user_phone=r["user_phone"], status=status,
            pickup_from=r["pickup_from"], pickup_to=r["pickup_to"],
            created_at=r["created_at"],
        )

    @staticmethod
    def _effective_status(stored: str, pickup_to: str) -> str:
        """Заказ со статусом paid, чьё окно выдачи прошло, считается просроченным."""
        if stored == "paid" and _is_past(pickup_to):
            return "expired"
        return stored

    def create_order(self, order_id: str, code: str, box: Box, name: str, phone: str,
                     code_factory=None) -> Order | None:
        """Создать заказ; при коллизии кода берёт новый из code_factory."""
        if _is_past(box.pickup_to):
            return None                     # окно самовывоза уже закрылось
        with self._lock, self._conn() as c:
            if not self._take_one(c, box.id):
                return None                 # боксы закончились
            for _ in range(5):
                try:
                    c.execute(
                        """INSERT INTO orders(id,code,box_id,partner_id,category,price,
                               user_name,user_phone,status,pickup_from,pickup_to,created_at)
                           VALUES(?,?,?,?,?,?,?,?, 'paid', ?,?,?)""",
                        (order_id, code, box.id, box.partner_id, box.category, box.price,
                         name, phone, box.pickup_from, box.pickup_to, _now_iso()),
                    )
                    break
                except sqlite3.IntegrityError:
                    if code_factory is None:
                        raise
                    code = code_factory()
            r = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            return self._order_from_row(c, r)

    def order_by_code(self, code: str) -> Order | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE code=?", (code.strip().upper(),)).fetchone()
            return self._order_from_row(c, r) if r else None

    def orders(self) -> list[Order]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
            return [self._order_from_row(c, r) for r in rows]

    def partner_orders(self, partner_id: str) -> list[Order]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM orders WHERE partner_id=? ORDER BY created_at DESC",
                (partner_id,),
            ).fetchall()
            return [self._order_from_row(c, r) for r in rows]

    def redeem(self, code: str) -> tuple[bool, str, Order | None]:
        """Выдать заказ по коду. Возвращает (ок, сообщение, заказ)."""
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE code=?", (code.strip().upper(),)).fetchone()
            if not r:
                return False, "Заказ с таким кодом не найден", None
            eff = self._effective_status(r["status"], r["pickup_to"])
            if eff == "issued":
                return False, "Этот заказ уже выдан", self._order_from_row(c, r)
            if eff in ("refunded", "cancelled"):
                return False, "Заказ отменён/возвращён", self._order_from_row(c, r)
            if eff == "expired":
                return False, "Окно выдачи истекло (no-show)", self._order_from_row(c, r)
            c.execute("UPDATE orders SET status='issued' WHERE id=?", (r["id"],))
            r2 = c.execute("SELECT * FROM orders WHERE id=?", (r["id"],)).fetchone()
            return True, "Выдано ✓", self._order_from_row(c, r2)

    def refund(self, order_id: str) -> bool:
        """Возврат (вина партнёра): вернуть бокс в наличие, статус refunded."""
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if not r or r["status"] in ("issued", "refunded", "cancelled"):
                return False
            c.execute("UPDATE orders SET status='refunded' WHERE id=?", (order_id,))
            # бокс возвращается в наличие только пока окно самовывоза не закрылось
            if not _is_past(r["pickup_to"]):
                self._return_one(c, r["box_id"])
            return True

    def cancel(self, code: str) -> tuple[bool, str]:
        """Отмена брони покупателем: доступна пока заказ оплачен и окно не истекло."""
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE code=?", (code.strip().upper(),)).fetchone()
            if not r:
                return False, "Заказ не найден"
            eff = self._effective_status(r["status"], r["pickup_to"])
            if eff != "paid":
                return False, "Отменить можно только активный оплаченный заказ"
            c.execute("UPDATE orders SET status='cancelled' WHERE id=?", (r["id"],))
            self._return_one(c, r["box_id"])
            return True, "Заказ отменён, бокс вернулся в продажу"

    # ------------------------------------------------------------------ #
    #  Статистика и сервис
    # ------------------------------------------------------------------ #
    def stats(self) -> dict:
        with self._lock, self._conn() as c:
            orders = c.execute("SELECT status, pickup_to, price FROM orders").fetchall()
        gmv = 0
        issued = no_show = active = refunds = 0
        for o in orders:
            st = self._effective_status(o["status"], o["pickup_to"])
            if st in ("paid", "issued"):
                gmv += o["price"]
            if st == "issued":
                issued += 1
            elif st == "expired":
                no_show += 1
            elif st == "paid":
                active += 1
            elif st == "refunded":
                refunds += 1
        total = len(orders)
        return {
            "orders_total": total, "issued": issued, "active": active,
            "no_show": no_show, "refunds": refunds, "gmv": gmv,
            "fill_rate": round(issued / total * 100) if total else 0,
        }

    def count(self) -> tuple[int, int, int]:
        with self._lock, self._conn() as c:
            p = c.execute("SELECT COUNT(*) FROM partners").fetchone()[0]
            b = c.execute("SELECT COUNT(*) FROM boxes").fetchone()[0]
            o = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        return p, b, o

    def reset(self) -> None:
        with self._lock, self._conn() as c:
            c.executescript("DELETE FROM partners; DELETE FROM boxes; DELETE FROM orders;")
