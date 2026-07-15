"""SQLite-хранилище: партнёры, боксы, заказы.

Продакшен-настройки: WAL (параллельные читатели не блокируют писателя),
busy_timeout (вместо мгновенного «database is locked»), foreign keys, индексы
под реальные запросы. Путь к файлу — env YUMMY_DB_PATH (persistent-диск на
хостинге), по умолчанию — рядом с проектом.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from .database import Database
from .models import Box, Order, Partner, Payment, RefundRequest, Review

_DB = Path(os.getenv("YUMMY_DB_PATH", str(Path(__file__).parent.parent / "spasibox.db")))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Repository over SQLite locally or PostgreSQL in production."""

    def __init__(self, path: Path | None = None, database_url: str | None = None) -> None:
        self._path = Path(path or _DB)
        self._database = Database(
            self._path, database_url, use_env=path is None and database_url is None
        )
        self._lock = threading.RLock()
        if not self._database.is_postgres:
            self._init_sqlite()

    def _conn(self):
        return self._database.connect()

    def _init_sqlite(self) -> None:
        with self._lock, self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS partners(
                    id TEXT PRIMARY KEY, name TEXT, district TEXT, address TEXT,
                    rating REAL, lat REAL, lng REAL, owner_user_id TEXT);
                CREATE TABLE IF NOT EXISTS boxes(
                    id TEXT PRIMARY KEY,
                    partner_id TEXT REFERENCES partners(id),
                    category TEXT, title TEXT,
                    price INTEGER, value_est INTEGER, qty_total INTEGER, qty_left INTEGER,
                    pickup_from TEXT, pickup_to TEXT, description TEXT, created_at TEXT,
                    status TEXT DEFAULT 'active');
                CREATE TABLE IF NOT EXISTS orders(
                    id TEXT PRIMARY KEY, code TEXT UNIQUE,
                    box_id TEXT REFERENCES boxes(id),
                    partner_id TEXT REFERENCES partners(id),
                    category TEXT, price INTEGER, user_name TEXT, user_phone TEXT,
                    status TEXT, pickup_from TEXT, pickup_to TEXT, created_at TEXT,
                    user_id TEXT, payment_status TEXT DEFAULT 'paid',
                    reservation_expires_at TEXT);
                CREATE TABLE IF NOT EXISTS reviews(
                    id TEXT PRIMARY KEY,
                    partner_id TEXT REFERENCES partners(id),
                    order_id TEXT UNIQUE REFERENCES orders(id),
                    user_id TEXT, author_name TEXT,
                    rating INTEGER, text TEXT,
                    status TEXT DEFAULT 'approved', reject_reason TEXT,
                    created_at TEXT);
                CREATE TABLE IF NOT EXISTS payments(
                    id TEXT PRIMARY KEY, order_id TEXT UNIQUE REFERENCES orders(id),
                    user_id TEXT, provider TEXT, status TEXT, currency TEXT,
                    amount_minor INTEGER, checkout_session_id TEXT UNIQUE,
                    payment_intent_id TEXT UNIQUE, idempotency_key TEXT UNIQUE,
                    reservation_expires_at TEXT, created_at TEXT, updated_at TEXT);
                CREATE TABLE IF NOT EXISTS stripe_events(
                    event_id TEXT PRIMARY KEY, event_type TEXT, payload_hash TEXT,
                    received_at TEXT, processed_at TEXT, status TEXT, error TEXT);
                CREATE TABLE IF NOT EXISTS refund_requests(
                    id TEXT PRIMARY KEY,
                    order_id TEXT UNIQUE REFERENCES orders(id),
                    user_id TEXT, partner_id TEXT,
                    reason TEXT, details TEXT, status TEXT DEFAULT 'pending',
                    resolution TEXT DEFAULT '', created_at TEXT, updated_at TEXT,
                    resolved_by TEXT);
                CREATE INDEX IF NOT EXISTS ix_boxes_partner  ON boxes(partner_id);
                CREATE INDEX IF NOT EXISTS ix_boxes_status   ON boxes(status, qty_left);
                CREATE INDEX IF NOT EXISTS ix_orders_partner ON orders(partner_id, created_at);
                CREATE INDEX IF NOT EXISTS ix_orders_user    ON orders(user_id, created_at);
                CREATE INDEX IF NOT EXISTS ix_orders_status  ON orders(status);
                CREATE INDEX IF NOT EXISTS ix_reviews_partner ON reviews(partner_id, status, created_at);
                CREATE INDEX IF NOT EXISTS ix_payments_status ON payments(status, reservation_expires_at);
                CREATE INDEX IF NOT EXISTS ix_payments_user ON payments(user_id, created_at);
                CREATE INDEX IF NOT EXISTS ix_refunds_user ON refund_requests(user_id, created_at);
                CREATE INDEX IF NOT EXISTS ix_refunds_status ON refund_requests(status, created_at);
                """
            )
            # Аддитивные миграции существующих БД.
            cols = {r[1] for r in c.execute("PRAGMA table_info(orders)").fetchall()}
            if "user_id" not in cols:
                c.execute("ALTER TABLE orders ADD COLUMN user_id TEXT")
            if "payment_status" not in cols:
                c.execute("ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT 'paid'")
            if "reservation_expires_at" not in cols:
                c.execute("ALTER TABLE orders ADD COLUMN reservation_expires_at TEXT")
            partner_cols = {r[1] for r in c.execute("PRAGMA table_info(partners)").fetchall()}
            if "owner_user_id" not in partner_cols:
                c.execute("ALTER TABLE partners ADD COLUMN owner_user_id TEXT")
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_partners_owner "
                      "ON partners(owner_user_id) WHERE owner_user_id IS NOT NULL")

    # ------------------------------------------------------------------ #
    #  Партнёры
    # ------------------------------------------------------------------ #
    def partners(self) -> list[Partner]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM partners ORDER BY name").fetchall()
        return [Partner(**dict(r)) for r in rows]

    def partner(self, partner_id: str) -> Partner | None:
        with self._lock, self._conn() as c:
            row = self._partner_row(c, partner_id)
            return Partner(**dict(row)) if row else None

    def partner_owned_by(self, partner_id: str, user_id: str) -> bool:
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT 1 FROM partners WHERE id=? AND owner_user_id=?",
                (partner_id, user_id),
            ).fetchone()
            return row is not None

    def _partner_row(self, c: sqlite3.Connection, pid: str) -> sqlite3.Row | None:
        return c.execute("SELECT * FROM partners WHERE id=?", (pid,)).fetchone()

    def upsert_partner(self, p: Partner, *, owner_user_id: str | None = None) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO partners(id,name,district,address,rating,lat,lng,owner_user_id)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                       district=excluded.district, address=excluded.address,
                       rating=excluded.rating, lat=excluded.lat, lng=excluded.lng,
                       owner_user_id=COALESCE(partners.owner_user_id, excluded.owner_user_id)""",
                (p.id, p.name, p.district, p.address, p.rating, p.lat, p.lng,
                 owner_user_id),
            )

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

    def box_orderability(self, box_id: str) -> str:
        """Причина недоступности: available / missing / sold_out / expired."""
        with self._lock, self._conn() as c:
            row = c.execute("SELECT status,qty_left,pickup_to FROM boxes WHERE id=?",
                            (box_id,)).fetchone()
        if not row or row["status"] != "active":
            return "missing"
        if row["qty_left"] <= 0:
            return "sold_out"
        if not self._pickup_is_open(row["pickup_to"]):
            return "expired"
        return "available"

    @staticmethod
    def _pickup_is_open(pickup_to: str) -> bool:
        try:
            end = datetime.fromisoformat(pickup_to.replace("Z", "+00:00"))
            if end.tzinfo is None:
                return False
            return end > datetime.now(timezone.utc)
        except (AttributeError, TypeError, ValueError):
            return False

    def boxes_available(self, district: str | None = None) -> list[Box]:
        self.expire_payment_reservations()
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM boxes WHERE status='active' AND qty_left>0 "
                "ORDER BY created_at DESC"
            ).fetchall()
            # ISO-строки могут иметь разные UTC-offset; сравнение делаем как
            # datetime, а не лексикографически в SQL.
            boxes = [self._box_from_row(c, r) for r in rows
                     if self._pickup_is_open(r["pickup_to"])]
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
        if stored == "paid" and not Store._pickup_is_open(pickup_to):
            # Malformed legacy timestamp трактуется fail-closed: выдать такой
            # заказ нельзя до ручной проверки, а не оставлять paid навсегда.
            return "expired"
        return stored

    def create_order(self, order_id: str, code: str, box: Box, name: str, phone: str,
                     user_id: str | None = None) -> Order | None:
        """Создать заказ в одной транзакции с резервированием остатка.

        Перед записью перечитываем authoritative box: вызывающий код мог получить
        устаревший объект, а окно выдачи могло закрыться между GET и POST.
        """
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM boxes WHERE id=?", (box.id,)).fetchone()
            if (not row or row["status"] != "active" or row["qty_left"] <= 0
                    or not self._pickup_is_open(row["pickup_to"])):
                return None
            actual = self._box_from_row(c, row)
            if not self._take_one(c, actual.id):
                return None                 # конкурент успел забрать последний
            c.execute(
                """INSERT INTO orders(id,code,box_id,partner_id,category,price,
                       user_name,user_phone,status,pickup_from,pickup_to,created_at,user_id)
                   VALUES(?,?,?,?,?,?,?,?, 'paid', ?,?,?,?)""",
                (order_id, code, actual.id, actual.partner_id, actual.category,
                 actual.price, name, phone, actual.pickup_from, actual.pickup_to,
                 _now_iso(), user_id),
            )
            r = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            return self._order_from_row(c, r)

    def create_checkout_reservation(
        self, payment_id: str, order_id: str, code: str, box: Box,
        name: str, phone: str, user_id: str | None, currency: str,
        ttl_seconds: int = 900,
    ) -> tuple[Order, Payment] | None:
        from datetime import timedelta
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM boxes WHERE id=?", (box.id,)).fetchone()
            if (not row or row["status"] != "active" or row["qty_left"] <= 0
                    or not self._pickup_is_open(row["pickup_to"])):
                return None
            actual = self._box_from_row(c, row)
            if not self._take_one(c, actual.id):
                return None
            now = datetime.now(timezone.utc)
            created = now.isoformat()
            expires = (now + timedelta(seconds=ttl_seconds)).isoformat()
            c.execute(
                """INSERT INTO orders(id,code,box_id,partner_id,category,price,
                       user_name,user_phone,status,pickup_from,pickup_to,created_at,user_id,
                       payment_status,reservation_expires_at)
                   VALUES(?,?,?,?,?,?,?,?,'payment_pending',?,?,?,?,'pending',?)""",
                (order_id, code, actual.id, actual.partner_id, actual.category, actual.price,
                 name, phone, actual.pickup_from, actual.pickup_to, created, user_id, expires),
            )
            idempotency_key = f"checkout:{payment_id}:1"
            c.execute(
                """INSERT INTO payments(id,order_id,user_id,provider,status,currency,
                       amount_minor,idempotency_key,reservation_expires_at,created_at,updated_at)
                   VALUES(?,?,?,'stripe','pending',?,?,?,?,?,?)""",
                (payment_id, order_id, user_id, currency, actual.price * 100,
                 idempotency_key, expires, created, created),
            )
            order_row = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            payment_row = c.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
            return self._order_from_row(c, order_row), Payment(**dict(payment_row))

    def attach_checkout_session(self, payment_id: str, session_id: str) -> bool:
        with self._lock, self._conn() as c:
            updated = c.execute(
                "UPDATE payments SET checkout_session_id=?,updated_at=? WHERE id=? AND status='pending'",
                (session_id, _now_iso(), payment_id),
            )
            return updated.rowcount == 1

    def fail_checkout_reservation(self, payment_id: str) -> bool:
        with self._lock, self._conn() as c:
            payment = c.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone()
            if not payment or payment["status"] != "pending":
                return False
            order = c.execute("SELECT * FROM orders WHERE id=?", (payment["order_id"],)).fetchone()
            c.execute("UPDATE payments SET status='failed',updated_at=? WHERE id=?", (_now_iso(), payment_id))
            c.execute("UPDATE orders SET status='payment_failed',payment_status='failed' WHERE id=?", (order["id"],))
            self._return_one(c, order["box_id"])
            return True

    def expire_payment_reservations(self) -> int:
        now = _now_iso()
        expired = 0
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM payments WHERE status='pending' AND reservation_expires_at<?",
                (now,),
            ).fetchall()
            for payment in rows:
                updated = c.execute(
                    "UPDATE payments SET status='expired',updated_at=? WHERE id=? AND status='pending'",
                    (now, payment["id"]),
                )
                if updated.rowcount != 1:
                    continue
                order = c.execute("SELECT * FROM orders WHERE id=?", (payment["order_id"],)).fetchone()
                c.execute("UPDATE orders SET status='payment_failed',payment_status='expired' WHERE id=? AND status='payment_pending'", (order["id"],))
                self._return_one(c, order["box_id"])
                expired += 1
        return expired

    def checkout_status(self, session_id: str) -> tuple[Payment, Order] | None:
        with self._lock, self._conn() as c:
            payment = c.execute("SELECT * FROM payments WHERE checkout_session_id=?", (session_id,)).fetchone()
            if not payment:
                return None
            order = c.execute("SELECT * FROM orders WHERE id=?", (payment["order_id"],)).fetchone()
            return Payment(**dict(payment)), self._order_from_row(c, order)

    def process_stripe_event(self, event: dict, payload_hash: str) -> str:
        event_id, event_type = event.get("id", ""), event.get("type", "")
        obj = event.get("data", {}).get("object", {})
        with self._lock, self._conn() as c:
            inserted = c.execute(
                """INSERT INTO stripe_events(event_id,event_type,payload_hash,received_at,status)
                   VALUES(?,?,?,?,'processing') ON CONFLICT(event_id) DO NOTHING""",
                (event_id, event_type, payload_hash, _now_iso()),
            )
            if inserted.rowcount != 1:
                return "duplicate"
            payment_id = (obj.get("metadata") or {}).get("payment_id")
            payment = c.execute("SELECT * FROM payments WHERE id=?", (payment_id,)).fetchone() if payment_id else None
            if not payment:
                c.execute("UPDATE stripe_events SET status='ignored',processed_at=? WHERE event_id=?", (_now_iso(), event_id))
                return "ignored"
            if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
                valid = (obj.get("payment_status") == "paid"
                         and int(obj.get("amount_total") or -1) == payment["amount_minor"]
                         and str(obj.get("currency") or "").lower() == payment["currency"]
                         and obj.get("client_reference_id") == payment["order_id"])
                if not valid:
                    c.execute("UPDATE stripe_events SET status='rejected',error='reconciliation',processed_at=? WHERE event_id=?", (_now_iso(), event_id))
                    return "rejected"
                c.execute("UPDATE payments SET status='paid',payment_intent_id=?,updated_at=? WHERE id=? AND status='pending'", (obj.get("payment_intent"), _now_iso(), payment_id))
                c.execute("UPDATE orders SET status='paid',payment_status='paid' WHERE id=? AND status='payment_pending'", (payment["order_id"],))
                result = "paid"
            elif event_type in {"checkout.session.expired", "checkout.session.async_payment_failed"}:
                order = c.execute("SELECT * FROM orders WHERE id=?", (payment["order_id"],)).fetchone()
                if payment["status"] == "pending":
                    c.execute("UPDATE payments SET status='expired',updated_at=? WHERE id=?", (_now_iso(), payment_id))
                    c.execute("UPDATE orders SET status='payment_failed',payment_status='expired' WHERE id=?", (order["id"],))
                    self._return_one(c, order["box_id"])
                result = "expired"
            else:
                result = "ignored"
            c.execute("UPDATE stripe_events SET status=?,processed_at=? WHERE event_id=?", (result, _now_iso(), event_id))
            return result

    def scrub_user(self, user_id: str) -> int:
        """Privacy: анонимизировать PII в заказах удалённого аккаунта
        (строки остаются — статистика партнёров не ломается)."""
        with self._lock, self._conn() as c:
            cur = c.execute(
                "UPDATE orders SET user_name='(удалён)', user_phone='' WHERE user_id=?",
                (user_id,),
            )
            return cur.rowcount

    def user_orders(self, user_id: str) -> list[Order]:
        """Заказы аккаунта — основа «/me/orders» (кросс-девайс история)."""
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [self._order_from_row(c, r) for r in rows]

    def order_by_code(self, code: str) -> Order | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE code=?", (code.strip().upper(),)).fetchone()
            return self._order_from_row(c, r) if r else None

    def order_by_id(self, order_id: str) -> Order | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            return self._order_from_row(c, r) if r else None

    def orders(self) -> list[Order]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
            return [self._order_from_row(c, r) for r in rows]

    def suspend_partner(self, partner_id: str) -> int:
        """Снять активный inventory при suspension/rejection аккаунта."""
        with self._lock, self._conn() as c:
            cur = c.execute(
                "UPDATE boxes SET status='suspended' WHERE partner_id=? AND status='active'",
                (partner_id,),
            )
            return cur.rowcount

    def partner_orders(self, partner_id: str) -> list[Order]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM orders WHERE partner_id=? ORDER BY created_at DESC",
                (partner_id,),
            ).fetchall()
            return [self._order_from_row(c, r) for r in rows]

    def redeem(self, code: str, *, partner_id: str | None = None) -> tuple[bool, str, Order | None]:
        """Выдать заказ по коду.

        ``partner_id`` ограничивает операцию tenant'ом. ``None`` разрешён только
        для доверенного admin/internal вызова на уровне API.
        """
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE code=?", (code.strip().upper(),)).fetchone()
            if not r or (partner_id is not None and r["partner_id"] != partner_id):
                # Не подтверждаем чужому заведению существование валидного кода.
                return False, "Заказ с таким кодом не найден", None
            eff = self._effective_status(r["status"], r["pickup_to"])
            if eff == "issued":
                return False, "Этот заказ уже выдан", self._order_from_row(c, r)
            if eff in ("refunded", "cancelled"):
                return False, "Заказ отменён/возвращён", self._order_from_row(c, r)
            if eff == "expired":
                return False, "Окно выдачи истекло (no-show)", self._order_from_row(c, r)
            updated = c.execute(
                "UPDATE orders SET status='issued' WHERE id=? AND status='paid'",
                (r["id"],),
            )
            r2 = c.execute("SELECT * FROM orders WHERE id=?", (r["id"],)).fetchone()
            if updated.rowcount != 1:
                # Другой worker/process успел выдать после нашего SELECT.
                return False, "Этот заказ уже выдан", self._order_from_row(c, r2)
            return True, "Выдано ✓", self._order_from_row(c, r2)

    def refund(self, order_id: str) -> bool:
        """Возврат (вина партнёра): вернуть бокс в наличие, статус refunded."""
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            if not r or r["status"] in ("issued", "refunded", "cancelled"):
                return False
            updated = c.execute(
                "UPDATE orders SET status='refunded' "
                "WHERE id=? AND status NOT IN ('issued','refunded','cancelled')",
                (order_id,),
            )
            if updated.rowcount != 1:
                return False
            self._return_one(c, r["box_id"])
            return True

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
            # No-show оплачен и по правилам не возвращается — это оборот.
            if st in ("paid", "issued", "expired"):
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
        closed = issued + no_show
        return {
            "orders_total": total, "issued": issued, "active": active,
            "no_show": no_show, "refunds": refunds, "gmv": gmv,
            # Активные и refunded не должны занижать операционный выкуп.
            "fill_rate": round(issued / closed * 100) if closed else 0,
        }

    def ping(self) -> bool:
        with self._conn() as connection:
            return connection.execute("SELECT 1").fetchone()[0] == 1

    def count(self) -> tuple[int, int, int]:
        with self._lock, self._conn() as c:
            p = c.execute("SELECT COUNT(*) FROM partners").fetchone()[0]
            b = c.execute("SELECT COUNT(*) FROM boxes").fetchone()[0]
            o = c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
        return p, b, o

    def reset(self) -> None:
        with self._lock, self._conn() as c:
            # Порядок учитывает foreign keys и позволяет безопасно reseed'ить
            # непустую базу в dev/test окружении.
            c.executescript(
                "DELETE FROM reviews; DELETE FROM refund_requests; DELETE FROM stripe_events; "
                "DELETE FROM payments; DELETE FROM orders; "
                "DELETE FROM boxes; DELETE FROM partners;"
            )

    # ------------------------------------------------------------------ #
    #  Refund requests: customer opens, MFA-admin resolves atomically.
    # ------------------------------------------------------------------ #
    @staticmethod
    def _refund_from_row(row: sqlite3.Row) -> RefundRequest:
        return RefundRequest(**dict(row))

    def create_refund_request(self, request_id: str, order_id: str, user_id: str,
                              reason: str, details: str) -> RefundRequest | None:
        with self._lock, self._conn() as c:
            order = c.execute(
                "SELECT * FROM orders WHERE id=? AND user_id=?", (order_id, user_id)
            ).fetchone()
            if not order or self._effective_status(order["status"], order["pickup_to"]) not in {
                "paid", "expired"
            }:
                return None
            if reason in {"not_issued", "venue_closed"}:
                try:
                    pickup_from = datetime.fromisoformat(order["pickup_from"].replace("Z", "+00:00"))
                except (AttributeError, ValueError):
                    return None
                if datetime.now(timezone.utc) < pickup_from:
                    return None
            now = _now_iso()
            inserted = c.execute(
                """INSERT INTO refund_requests(
                       id,order_id,user_id,partner_id,reason,details,status,
                       resolution,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,'pending','',?,?)
                   ON CONFLICT(order_id) DO NOTHING""",
                (request_id, order_id, user_id, order["partner_id"], reason,
                 details, now, now),
            )
            if inserted.rowcount != 1:
                return None
            row = c.execute("SELECT * FROM refund_requests WHERE id=?", (request_id,)).fetchone()
            return self._refund_from_row(row)

    def user_refund_requests(self, user_id: str) -> list[RefundRequest]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM refund_requests WHERE user_id=? ORDER BY created_at DESC",
                (user_id,),
            ).fetchall()
            return [self._refund_from_row(r) for r in rows]

    def refund_requests(self, status: str | None = None) -> list[RefundRequest]:
        with self._lock, self._conn() as c:
            if status:
                rows = c.execute(
                    "SELECT * FROM refund_requests WHERE status=? ORDER BY created_at", (status,)
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM refund_requests ORDER BY created_at DESC"
                ).fetchall()
            return [self._refund_from_row(r) for r in rows]

    def resolve_refund_request(self, request_id: str, action: str, resolution: str,
                               admin_id: str) -> RefundRequest | None:
        with self._lock, self._conn() as c:
            req = c.execute("SELECT * FROM refund_requests WHERE id=?", (request_id,)).fetchone()
            if not req or req["status"] not in {"pending", "reviewing"}:
                return None
            now = _now_iso()
            if action == "reviewing":
                status = "reviewing"
            elif action == "reject":
                status = "rejected"
            elif action == "approve":
                order = c.execute("SELECT * FROM orders WHERE id=?", (req["order_id"],)).fetchone()
                if not order:
                    return None
                updated = c.execute(
                    "UPDATE orders SET status='refunded' WHERE id=? AND status='paid'",
                    (order["id"],),
                )
                if updated.rowcount != 1:
                    return None
                self._return_one(c, order["box_id"])
                status = "refunded"
            else:
                return None
            c.execute(
                """UPDATE refund_requests SET status=?,resolution=?,updated_at=?,resolved_by=?
                   WHERE id=?""",
                (status, resolution, now, admin_id, request_id),
            )
            row = c.execute("SELECT * FROM refund_requests WHERE id=?", (request_id,)).fetchone()
            return self._refund_from_row(row)

    # ------------------------------------------------------------------ #
    #  Отзывы (только по завершённому — issued — заказу; одна ревью на заказ)
    # ------------------------------------------------------------------ #
    def _review_from_row(self, r: sqlite3.Row) -> Review:
        return Review(
            id=r["id"], partner_id=r["partner_id"], order_id=r["order_id"],
            author_name=r["author_name"], rating=r["rating"], text=r["text"],
            status=r["status"], created_at=r["created_at"],
        )

    def has_review(self, order_id: str) -> bool:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT 1 FROM reviews WHERE order_id=?", (order_id,)).fetchone()
            return r is not None

    def create_review(self, review_id: str, partner_id: str, order_id: str,
                      user_id: str | None, author_name: str, rating: int, text: str,
                      status: str, reject_reason: str = "") -> Review:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO reviews(id,partner_id,order_id,user_id,author_name,
                       rating,text,status,reject_reason,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (review_id, partner_id, order_id, user_id, author_name, rating,
                 text, status, reject_reason, _now_iso()),
            )
            r = c.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
            return self._review_from_row(r)

    def partner_reviews(self, partner_id: str, limit: int = 20) -> list[Review]:
        """Только одобренные — публичная витрина."""
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM reviews WHERE partner_id=? AND status='approved' "
                "ORDER BY created_at DESC LIMIT ?",
                (partner_id, limit),
            ).fetchall()
            return [self._review_from_row(r) for r in rows]

    # ------------------------------------------------------------------ #
    #  Рекомендации: без AI — частота категорий/заведений в истории заказов
    # ------------------------------------------------------------------ #
    def recommend_boxes(self, user_id: str, limit: int = 4) -> list[Box]:
        history = self.user_orders(user_id)
        available = self.boxes_available(None)
        if not history:
            # нет истории — просто скоро закрывающиеся окна (тот же принцип, что в UI)
            return sorted(available, key=lambda b: b.pickup_to)[:limit]
        cat_count: dict[str, int] = {}
        partner_count: dict[str, int] = {}
        for o in history:
            cat_count[o.category] = cat_count.get(o.category, 0) + 1
            partner_count[o.partner_id] = partner_count.get(o.partner_id, 0) + 1

        def score(b: Box) -> tuple[int, str]:
            s = cat_count.get(b.category, 0) * 2 + partner_count.get(b.partner_id, 0) * 3
            return (-s, b.pickup_to)  # выше очки — раньше; при равенстве — скорее закрывается

        return sorted(available, key=score)[:limit]
