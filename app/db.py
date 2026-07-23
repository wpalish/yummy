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
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import credvault, database
from .models import Box, Order, Partner, Review

_DB = Path(os.getenv("YUMMY_DB_PATH", str(Path(__file__).parent.parent / "spasibox.db")))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    """Потокобезопасная обёртка над SQLite."""

    def __init__(self, path: Path = _DB) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init()

    @contextmanager
    def _conn(self):
        # Postgres (Supabase) при DATABASE_URL — общий пул; иначе SQLite по пути
        # инстанса (тесты изолированы своим tmp-файлом).
        if database.POSTGRES:
            with database.connection() as c:
                yield c
            return
        c = sqlite3.connect(self._path, timeout=5.0)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000")
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("PRAGMA synchronous=NORMAL")  # безопасно с WAL, заметно быстрее FULL
        try:
            with c:
                yield c
        finally:
            c.close()

    def _init(self) -> None:
        with self._lock, self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS partners(
                    id TEXT PRIMARY KEY, name TEXT, district TEXT, address TEXT,
                    rating REAL, lat REAL, lng REAL);
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
                    user_id TEXT,
                    payment_status TEXT DEFAULT 'not_required');
                CREATE TABLE IF NOT EXISTS reviews(
                    id TEXT PRIMARY KEY,
                    partner_id TEXT REFERENCES partners(id),
                    order_id TEXT UNIQUE REFERENCES orders(id),
                    user_id TEXT, author_name TEXT,
                    rating INTEGER, text TEXT,
                    status TEXT DEFAULT 'approved', reject_reason TEXT,
                    created_at TEXT);
                CREATE TABLE IF NOT EXISTS tg_subscribers(
                    chat_id INTEGER PRIMARY KEY, name TEXT, created_at TEXT);
                CREATE TABLE IF NOT EXISTS meta(
                    key TEXT PRIMARY KEY, value TEXT);
                CREATE TABLE IF NOT EXISTS box_templates(
                    id TEXT PRIMARY KEY,
                    partner_id TEXT REFERENCES partners(id),
                    category TEXT, title TEXT, price INTEGER, value_est INTEGER,
                    qty INTEGER, hours INTEGER, description TEXT, created_at TEXT);
                -- Платёжный мерчант-аккаунт партнёра (деньги идут напрямую ему,
                -- Yummy денег не хранит). public_id — несекретный UUID для webhook-URL.
                CREATE TABLE IF NOT EXISTS partner_payment_accounts(
                    id TEXT PRIMARY KEY, partner_id TEXT UNIQUE REFERENCES partners(id),
                    public_id TEXT UNIQUE, provider TEXT DEFAULT 'kaspi',
                    merchant_reference TEXT, status TEXT DEFAULT 'pending',
                    payments_enabled INTEGER DEFAULT 0, refunds_enabled INTEGER DEFAULT 0,
                    created_at TEXT, verified_at TEXT);
                -- Ставка комиссии в basis points (10% = 1000 bps), фиксируется в момент оплаты.
                CREATE TABLE IF NOT EXISTS commission_rules(
                    id TEXT PRIMARY KEY, partner_id TEXT REFERENCES partners(id),
                    rate_bps INTEGER, valid_from TEXT, created_at TEXT);
                -- Долг партнёра перед Yummy по каждому оплаченному заказу.
                CREATE TABLE IF NOT EXISTS commission_ledger(
                    id TEXT PRIMARY KEY, partner_id TEXT REFERENCES partners(id),
                    order_id TEXT UNIQUE REFERENCES orders(id),
                    gross_minor INTEGER, rate_bps INTEGER, commission_minor INTEGER,
                    status TEXT DEFAULT 'accrued', created_at TEXT, reversed_at TEXT);
                -- Счёт партнёру за период: агрегат accrued-строк ledger.
                CREATE TABLE IF NOT EXISTS commission_invoices(
                    id TEXT PRIMARY KEY, partner_id TEXT REFERENCES partners(id),
                    total_minor INTEGER, entries_count INTEGER,
                    period_from TEXT, period_to TEXT,
                    status TEXT DEFAULT 'open', created_at TEXT, paid_at TEXT);
                -- «Кого зовут»: сколько раз покупатели просили боксы у заведения
                -- из карты (venues.json). Только счётчик, без персональных данных.
                CREATE TABLE IF NOT EXISTS venue_interest(
                    venue_id TEXT PRIMARY KEY, name TEXT, address TEXT,
                    district TEXT, votes INTEGER DEFAULT 0, updated_at TEXT);
                CREATE INDEX IF NOT EXISTS ix_venue_interest ON venue_interest(votes);
                CREATE INDEX IF NOT EXISTS ix_boxes_partner  ON boxes(partner_id);
                CREATE INDEX IF NOT EXISTS ix_boxes_status   ON boxes(status, qty_left);
                CREATE INDEX IF NOT EXISTS ix_orders_partner ON orders(partner_id, created_at);
                CREATE INDEX IF NOT EXISTS ix_orders_user    ON orders(user_id, created_at);
                CREATE INDEX IF NOT EXISTS ix_orders_status  ON orders(status);
                CREATE INDEX IF NOT EXISTS ix_reviews_partner ON reviews(partner_id, status, created_at);
                """
            )
            # миграция существующих SQLite-БД (на PG — ADD COLUMN IF NOT EXISTS).
            if database.POSTGRES:
                c.execute("ALTER TABLE commission_ledger ADD COLUMN IF NOT EXISTS invoice_id TEXT")
                c.execute("ALTER TABLE orders ADD COLUMN IF NOT EXISTS invoice_id TEXT")
            else:
                cols = {r[1] for r in c.execute("PRAGMA table_info(orders)").fetchall()}
                if "payment_status" not in cols:
                    c.execute("ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT 'not_required'")
                if "user_id" not in cols:
                    c.execute("ALTER TABLE orders ADD COLUMN user_id TEXT")
                if "invoice_id" not in cols:                 # id инвойса ApiPay/Kaspi
                    c.execute("ALTER TABLE orders ADD COLUMN invoice_id TEXT")
                lcols = {r[1] for r in c.execute("PRAGMA table_info(commission_ledger)").fetchall()}
                if "invoice_id" not in lcols:
                    c.execute("ALTER TABLE commission_ledger ADD COLUMN invoice_id TEXT")

    # ------------------------------------------------------------------ #
    #  Партнёры
    # ------------------------------------------------------------------ #
    def partners(self) -> list[Partner]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM partners ORDER BY name").fetchall()
        return [Partner(**dict(r)) for r in rows]

    def _partner_row(self, c: sqlite3.Connection, pid: str) -> sqlite3.Row | None:
        return c.execute("SELECT * FROM partners WHERE id=?", (pid,)).fetchone()

    def partner(self, pid: str) -> Partner | None:
        with self._lock, self._conn() as c:
            r = self._partner_row(c, pid)
        return Partner(**dict(r)) if r else None

    # ---- «Кого зовут»: спрос на заведения из карты ------------------------- #
    def add_venue_interest(self, venue_id: str, name: str,
                           address: str = "", district: str = "") -> int:
        """+1 к спросу на заведение. Возвращает новый счётчик."""
        now = datetime.now(timezone.utc).isoformat()
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO venue_interest(venue_id,name,address,district,votes,updated_at)
                   VALUES(?,?,?,?,1,?)
                   ON CONFLICT(venue_id) DO UPDATE SET
                       votes=venue_interest.votes+1, updated_at=excluded.updated_at""",
                (venue_id, name, address, district, now),
            )
            r = c.execute("SELECT votes FROM venue_interest WHERE venue_id=?",
                          (venue_id,)).fetchone()
        return int(r["votes"]) if r else 1

    def venue_interest_top(self, limit: int = 50) -> list[dict]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT venue_id,name,address,district,votes,updated_at FROM venue_interest"
                " ORDER BY votes DESC, updated_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def create_partner_for_owner(self, *, name: str, address: str,
                                 district: str = "Есильский р-н") -> str:
        """Завести карточку заведения при приёме инвайта владельцем."""
        pid = "p" + uuid.uuid4().hex[:8]
        self.upsert_partner(Partner(id=pid, name=name, district=district, address=address))
        return pid

    def upsert_partner(self, p: Partner) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO partners(id,name,district,address,rating,lat,lng)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                       district=excluded.district, address=excluded.address,
                       rating=excluded.rating, lat=excluded.lat, lng=excluded.lng""",
                (p.id, p.name, p.district, p.address, p.rating, p.lat, p.lng),
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

    def boxes_available(self, district: str | None = None) -> list[Box]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM boxes WHERE status='active' AND qty_left>0 "
                "ORDER BY created_at DESC"
            ).fetchall()
            boxes = [self._box_from_row(c, r) for r in rows]
        if district and district != "all":
            boxes = [b for b in boxes if b.district == district]
        return boxes

    def update_box(self, box_id: str, *, title: str | None = None,
                   description: str | None = None, price: int | None = None,
                   value_est: int | None = None, qty_total: int | None = None,
                   pickup_from: str | None = None, pickup_to: str | None = None,
                   ) -> Box | None:
        """Правка бокса партнёром. qty_left двигается на ту же дельту, что и
        qty_total (нельзя «отобрать» уже забронированные) и не уходит ниже 0."""
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM boxes WHERE id=?", (box_id,)).fetchone()
            if not r:
                return None
            new_total = r["qty_total"] if qty_total is None else max(1, qty_total)
            booked = r["qty_total"] - r["qty_left"]          # уже забронировано
            new_left = max(0, new_total - booked)
            c.execute(
                """UPDATE boxes SET title=?, description=?, price=?, value_est=?,
                       qty_total=?, qty_left=?, pickup_from=?, pickup_to=? WHERE id=?""",
                (r["title"] if title is None else title,
                 r["description"] if description is None else description,
                 r["price"] if price is None else price,
                 r["value_est"] if value_est is None else value_est,
                 new_total, new_left,
                 r["pickup_from"] if pickup_from is None else pickup_from,
                 r["pickup_to"] if pickup_to is None else pickup_to, box_id),
            )
            row = c.execute("SELECT * FROM boxes WHERE id=?", (box_id,)).fetchone()
            return self._box_from_row(c, row)

    def close_box(self, box_id: str) -> bool:
        """Снять бокс с продажи. Уже оплаченные заказы остаются в силе —
        их надо выдать, поэтому заказы не трогаем."""
        with self._lock, self._conn() as c:
            cur = c.execute(
                "UPDATE boxes SET status='closed', qty_left=0 WHERE id=? AND status='active'",
                (box_id,))
            return bool(getattr(cur, "rowcount", 0))

    def box_owner(self, box_id: str) -> str | None:
        """partner_id владельца бокса — для проверки прав перед правкой."""
        with self._lock, self._conn() as c:
            r = c.execute("SELECT partner_id FROM boxes WHERE id=?", (box_id,)).fetchone()
        return r["partner_id"] if r else None

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
            payment_status=(r["payment_status"] if "payment_status" in r.keys() else "not_required"),
            pickup_from=r["pickup_from"], pickup_to=r["pickup_to"],
            created_at=r["created_at"],
        )

    @staticmethod
    def _effective_status(stored: str, pickup_to: str) -> str:
        """Заказ со статусом paid, чьё окно выдачи прошло, считается просроченным."""
        if stored == "paid":
            try:
                if datetime.now(timezone.utc) > datetime.fromisoformat(pickup_to):
                    return "expired"
            except ValueError:
                pass
        return stored

    def create_order(self, order_id: str, code: str, box: Box, name: str, phone: str,
                     user_id: str | None = None, require_payment: bool = False) -> Order | None:
        """require_payment=True (партнёр с активным мерчант-аккаунтом): заказ
        создаётся payment_status='pending', QR/выдача — только после оплаты.
        Иначе (пилот без мерчанта) — 'not_required', как раньше."""
        pay = "pending" if require_payment else "not_required"
        with self._lock, self._conn() as c:
            if not self._take_one(c, box.id):
                return None                 # боксы закончились
            c.execute(
                """INSERT INTO orders(id,code,box_id,partner_id,category,price,
                       user_name,user_phone,status,pickup_from,pickup_to,created_at,user_id,payment_status)
                   VALUES(?,?,?,?,?,?,?,?, 'paid', ?,?,?,?,?)""",
                (order_id, code, box.id, box.partner_id, box.category, box.price,
                 name, phone, box.pickup_from, box.pickup_to, _now_iso(), user_id, pay),
            )
            r = c.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            return self._order_from_row(c, r)

    def confirm_payment(self, code: str) -> Order | None:
        """Подтвердить оплату (в проде — из подписанного Kaspi-webhook).
        pending → paid. Идемпотентно: повторное подтверждение не дублирует."""
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE code=?", (code.strip().upper(),)).fetchone()
            if not r or r["payment_status"] != "pending":
                return None
            c.execute("UPDATE orders SET payment_status='paid' WHERE id=?", (r["id"],))
            r2 = c.execute("SELECT * FROM orders WHERE id=?", (r["id"],)).fetchone()
            return self._order_from_row(c, r2)

    def set_order_invoice(self, order_id: str, invoice_id: str) -> None:
        """Привязать инвойс ApiPay к заказу — по нему вебхук найдёт заказ."""
        with self._lock, self._conn() as c:
            c.execute("UPDATE orders SET invoice_id=? WHERE id=?", (str(invoice_id), order_id))

    def confirm_payment_by_invoice(self, invoice_id: str) -> Order | None:
        """Путь Kaspi-webhook: находим заказ по invoice_id, pending → paid.
        Идемпотентно (повторный вебхук того же invoice не дублирует оплату)."""
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE invoice_id=?", (str(invoice_id),)).fetchone()
            if not r or r["payment_status"] != "pending":
                return None
            c.execute("UPDATE orders SET payment_status='paid' WHERE id=?", (r["id"],))
            r2 = c.execute("SELECT * FROM orders WHERE id=?", (r["id"],)).fetchone()
            return self._order_from_row(c, r2)

    def expire_overdue(self) -> int:
        """Материализовать no-show: paid-заказы с прошедшим окном выдачи →
        status='expired' в БД (раньше статус считался лениво при чтении, и
        строки навсегда оставались 'paid'). Возвращает число просроченных."""
        now = _now_iso()
        with self._lock, self._conn() as c:
            cur = c.execute(
                """UPDATE orders SET status='expired'
                   WHERE status='paid' AND payment_status!='pending' AND pickup_to < ?""",
                (now,))
            return getattr(cur, "rowcount", 0)

    def release_expired_pending(self, ttl_min: int = 15) -> int:
        """Резерв под неоплаченный заказ живёт ttl_min минут. Просрочен →
        бокс возвращается в продажу, заказ отменяется. Возвращает число снятых."""
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=ttl_min)).isoformat()
        released = 0
        with self._lock, self._conn() as c:
            rows = c.execute("""SELECT id, box_id FROM orders
                              WHERE payment_status='pending' AND status='paid'
                              AND created_at < ?""", (cutoff,)).fetchall()
            for row in rows:
                c.execute("UPDATE orders SET status='cancelled' WHERE id=?", (row["id"],))
                self._return_one(c, row["box_id"])
                released += 1
        return released

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

    def orders(self, limit: int = 200, offset: int = 0) -> list[Order]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM orders ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
            return [self._order_from_row(c, r) for r in rows]

    def partner_orders(self, partner_id: str, limit: int = 200,
                       offset: int = 0) -> list[Order]:
        with self._lock, self._conn() as c:
            rows = c.execute(
                "SELECT * FROM orders WHERE partner_id=? ORDER BY created_at DESC"
                " LIMIT ? OFFSET ?",
                (partner_id, limit, offset),
            ).fetchall()
            return [self._order_from_row(c, r) for r in rows]

    def partner_daily_stats(self, partner_id: str, days: int = 30) -> list[dict]:
        """Заказы партнёра по дням за последние `days` дней (для графика в кабинете).
        Выручка считается по paid/issued — отменённые/просроченные/возвращённые
        деньги не приносят, но статистику по ним показываем отдельно.
        """
        with self._lock, self._conn() as c:
            rows = c.execute(
                """
                SELECT substr(created_at,1,10) AS day,
                       COUNT(*) AS orders_count,
                       SUM(CASE WHEN status IN ('paid','issued') THEN price ELSE 0 END) AS revenue,
                       SUM(CASE WHEN status='issued' THEN 1 ELSE 0 END) AS issued_count,
                       SUM(CASE WHEN status IN ('cancelled','expired','refunded') THEN 1 ELSE 0 END) AS lost_count
                FROM orders
                WHERE partner_id=? AND date(created_at) >= date('now', ?)
                GROUP BY day
                ORDER BY day
                """,
                (partner_id, f"-{max(1, days) - 1} days"),
            ).fetchall()
            return [
                {
                    "day": r["day"],
                    "orders_count": r["orders_count"],
                    "revenue": r["revenue"] or 0,
                    "issued_count": r["issued_count"],
                    "lost_count": r["lost_count"],
                }
                for r in rows
            ]

    def redeem(self, code: str) -> tuple[bool, str, Order | None]:
        """Выдать заказ по коду. Возвращает (ок, сообщение, заказ)."""
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE code=?", (code.strip().upper(),)).fetchone()
            if not r:
                return False, "Заказ с таким кодом не найден", None
            if r["payment_status"] == "pending":
                return False, "Заказ ещё не оплачен", self._order_from_row(c, r)
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
            self._return_one(c, r["box_id"])
            return True

    @staticmethod
    def _window_started(pickup_from: str) -> bool:
        try:
            return datetime.now(timezone.utc) >= datetime.fromisoformat(pickup_from)
        except ValueError:
            return True  # битая дата — считаем окно начавшимся (запрет отмены безопаснее)

    def cancel_order(self, code: str) -> tuple[bool, str]:
        """Отмена брони покупателем ДО начала окна выдачи (идея из Devin PR #5).
        Владение подтверждает код заказа — та же модель доверия, что у /redeem.
        Бокс возвращается в продажу, статус cancelled."""
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE code=?", (code.strip().upper(),)).fetchone()
            if not r:
                return False, "Заказ с таким кодом не найден"
            if r["status"] != "paid":
                return False, "Этот заказ уже нельзя отменить"
            if self._window_started(r["pickup_from"]):
                return False, "Окно выдачи уже началось — отмена недоступна"
            c.execute("UPDATE orders SET status='cancelled' WHERE id=?", (r["id"],))
            self._return_one(c, r["box_id"])
            return True, "Бронь отменена, бокс вернулся в продажу"

    def refund_by_code(self, code: str) -> tuple[bool, str]:
        """Самостоятельный возврат «заказ не выдали»: доступен с начала окна.
        Раньше фронт звал /admin/refund — в проде с включённой авторизацией это
        401 для обычного покупателя; код заказа как подтверждение владения
        решает без админ-токена."""
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM orders WHERE code=?", (code.strip().upper(),)).fetchone()
            if not r:
                return False, "Заказ с таким кодом не найден"
            if r["status"] != "paid":
                return False, "Возврат по этому заказу недоступен"
            if not self._window_started(r["pickup_from"]):
                return False, "Окно выдачи ещё не началось — можно просто отменить бронь"
            c.execute("UPDATE orders SET status='refunded' WHERE id=?", (r["id"],))
            self._return_one(c, r["box_id"])
            return True, "Возврат оформлен — деньги вернутся на карту"

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

    # ------------------------------------------------------------------ #
    #  Telegram-подписчики и служебные метки (offset getUpdates)
    # ------------------------------------------------------------------ #
    def meta_get(self, key: str, default: str = "") -> str:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return r["value"] if r else default

    def meta_set(self, key: str, value: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("""INSERT INTO meta(key,value) VALUES(?,?)
                         ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
                      (key, value))

    def tg_add_subscriber(self, chat_id: int, name: str = "") -> bool:
        """True — подписчик новый, False — уже был."""
        with self._lock, self._conn() as c:
            cur = c.execute(
                "INSERT OR IGNORE INTO tg_subscribers(chat_id,name,created_at) VALUES(?,?,?)",
                (chat_id, name, _now_iso()))
        return cur.rowcount == 1

    def tg_remove_subscriber(self, chat_id: int) -> None:
        with self._lock, self._conn() as c:
            c.execute("DELETE FROM tg_subscribers WHERE chat_id=?", (chat_id,))

    def tg_subscribers(self) -> list[int]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT chat_id FROM tg_subscribers ORDER BY created_at").fetchall()
        return [r["chat_id"] for r in rows]

    # ------------------------------------------------------------------ #
    #  Шаблоны боксов: партнёр сохраняет и публикует одной кнопкой
    # ------------------------------------------------------------------ #
    def create_template(self, tid: str, data) -> dict:
        with self._lock, self._conn() as c:
            c.execute("""INSERT INTO box_templates(id,partner_id,category,title,price,
                         value_est,qty,hours,description,created_at)
                         VALUES(?,?,?,?,?,?,?,?,?,?)""",
                      (tid, data.partner_id, data.category, data.title, data.price,
                       data.value_est, data.qty, data.hours, data.description, _now_iso()))
        return self.template(tid)

    def template(self, tid: str) -> dict | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM box_templates WHERE id=?", (tid,)).fetchone()
        return dict(r) if r else None

    def partner_templates(self, partner_id: str) -> list[dict]:
        with self._lock, self._conn() as c:
            rows = c.execute("SELECT * FROM box_templates WHERE partner_id=? ORDER BY created_at DESC",
                             (partner_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_template(self, tid: str, partner_id: str) -> bool:
        with self._lock, self._conn() as c:
            cur = c.execute("DELETE FROM box_templates WHERE id=? AND partner_id=?",
                            (tid, partner_id))
        return cur.rowcount == 1

    # ------------------------------------------------------------------ #
    #  Платежи: мерчант-аккаунты партнёров + движок комиссий
    #  Деньги идут напрямую партнёру (его Kaspi), Yummy ведёт учёт долга.
    # ------------------------------------------------------------------ #
    _DEFAULT_RATE_BPS = 1000  # 10% по умолчанию

    def upsert_payment_account(self, aid: str, partner_id: str, public_id: str,
                               merchant_reference: str, provider: str = "kaspi") -> dict:
        # merchant_reference — чувствительный реквизит: в БД только шифртекст
        enc_ref = credvault.encrypt(merchant_reference)
        with self._lock, self._conn() as c:
            c.execute("""INSERT INTO partner_payment_accounts(id,partner_id,public_id,
                         provider,merchant_reference,status,created_at)
                         VALUES(?,?,?,?,?,'pending',?)
                         ON CONFLICT(partner_id) DO UPDATE SET
                           merchant_reference=excluded.merchant_reference,
                           provider=excluded.provider""",
                      (aid, partner_id, public_id, provider, enc_ref, _now_iso()))
        return self.payment_account(partner_id)

    def payment_account(self, partner_id: str) -> dict | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM partner_payment_accounts WHERE partner_id=?",
                          (partner_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        # расшифровка на лету; легаси-плейнтекст проходит как есть
        try:
            d["merchant_reference"] = credvault.decrypt(d.get("merchant_reference") or "")
        except ValueError:
            d["merchant_reference"] = ""      # ключ сменился без ротации — не 500
        return d

    def payment_accounts(self) -> list[dict]:
        """Все платёжные аккаунты для админки — реквизит сразу маскируем,
        полный номер из этого метода не выходит вообще."""
        with self._lock, self._conn() as c:
            rows = c.execute(
                """SELECT a.*, p.name AS partner_name FROM partner_payment_accounts a
                   LEFT JOIN partners p ON p.id=a.partner_id
                   ORDER BY a.created_at DESC""").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                ref = credvault.decrypt(d.pop("merchant_reference") or "")
            except ValueError:
                ref = ""
            d["merchant_masked"] = ("…" + ref[-4:]) if ref else ""
            d["encrypted"] = credvault.is_encrypted(r["merchant_reference"] or "")
            out.append(d)
        return out

    def set_payment_account_status(self, partner_id: str, status: str,
                                   payments_enabled: bool) -> dict | None:
        with self._lock, self._conn() as c:
            c.execute("""UPDATE partner_payment_accounts SET status=?, payments_enabled=?,
                         verified_at=? WHERE partner_id=?""",
                      (status, int(payments_enabled),
                       _now_iso() if status == "active" else None, partner_id))
        return self.payment_account(partner_id)

    def can_sell_paid(self, partner_id: str) -> bool:
        """Партнёр может продавать платные боксы только с активным аккаунтом."""
        a = self.payment_account(partner_id)
        return bool(a and a["status"] == "active" and a["payments_enabled"])

    def set_commission_rate(self, rid: str, partner_id: str, rate_bps: int) -> int:
        with self._lock, self._conn() as c:
            c.execute("""INSERT INTO commission_rules(id,partner_id,rate_bps,valid_from,created_at)
                         VALUES(?,?,?,?,?)""",
                      (rid, partner_id, rate_bps, _now_iso(), _now_iso()))
        return rate_bps

    def active_commission_bps(self, partner_id: str) -> int:
        with self._lock, self._conn() as c:
            r = c.execute("""SELECT rate_bps FROM commission_rules WHERE partner_id=?
                             ORDER BY valid_from DESC LIMIT 1""", (partner_id,)).fetchone()
        return r["rate_bps"] if r else self._DEFAULT_RATE_BPS

    @staticmethod
    def commission_minor(gross_minor: int, rate_bps: int) -> int:
        """Целочисленно, без float: округление вверх до тиына."""
        return (gross_minor * rate_bps + 9_999) // 10_000

    def accrue_commission(self, lid: str, order) -> dict | None:
        """Начислить комиссию по оплаченному заказу. Только если у партнёра
        активный платёжный аккаунт и ещё нет записи по этому заказу (одна на order)."""
        if not self.can_sell_paid(order.partner_id):
            return None
        bps = self.active_commission_bps(order.partner_id)
        gross = order.price * 100  # тг → тиын (минорные единицы)
        comm = self.commission_minor(gross, bps)
        with self._lock, self._conn() as c:
            cur = c.execute("""INSERT OR IGNORE INTO commission_ledger(id,partner_id,order_id,
                              gross_minor,rate_bps,commission_minor,status,created_at)
                              VALUES(?,?,?,?,?,?,'accrued',?)""",
                            (lid, order.partner_id, order.id, gross, bps, comm, _now_iso()))
            if cur.rowcount == 0:
                return None  # уже начислено
        return self.commission_entry(order.id)

    def reverse_commission(self, order_id: str) -> bool:
        with self._lock, self._conn() as c:
            cur = c.execute("""UPDATE commission_ledger SET status='reversed', reversed_at=?
                             WHERE order_id=? AND status='accrued'""", (_now_iso(), order_id))
        return cur.rowcount == 1

    def commission_entry(self, order_id: str) -> dict | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM commission_ledger WHERE order_id=?", (order_id,)).fetchone()
        return dict(r) if r else None

    def commission_summary(self, partner_id: str) -> dict:
        """Сколько партнёр должен Yummy: начислено минус сторнировано."""
        with self._lock, self._conn() as c:
            rows = c.execute("""SELECT status, COUNT(*) n, COALESCE(SUM(commission_minor),0) s
                              FROM commission_ledger WHERE partner_id=? GROUP BY status""",
                             (partner_id,)).fetchall()
        by = {r["status"]: {"count": r["n"], "minor": r["s"]} for r in rows}
        owed = by.get("accrued", {}).get("minor", 0)
        return {"owed_minor": owed, "owed_tenge": owed // 100, "by_status": by}

    def suspend_payment_account(self, partner_id: str) -> dict | None:
        """Приостановить приём платежей (нарушение/долг). Платные боксы
        публиковать нельзя, пока админ не активирует заново."""
        return self.set_payment_account_status(partner_id, "suspended",
                                               payments_enabled=False)

    def rotate_payment_public_id(self, partner_id: str) -> dict | None:
        """Сменить public_id (несекретный id для webhook-URL). Нужен при утечке
        URL: старые webhook-и перестают матчиться."""
        with self._lock, self._conn() as c:
            cur = c.execute("UPDATE partner_payment_accounts SET public_id=? WHERE partner_id=?",
                            (uuid.uuid4().hex, partner_id))
            if not getattr(cur, "rowcount", 0):
                return None
        return self.payment_account(partner_id)

    def rotate_merchant_reference(self, partner_id: str, new_reference: str) -> dict | None:
        """Смена реквизита мерчанта (перевыпуск в банке). Пишется уже новым
        ключом шифрования — заодно это и ротация ключа для этой записи."""
        if not self.payment_account(partner_id):
            return None
        with self._lock, self._conn() as c:
            c.execute("UPDATE partner_payment_accounts SET merchant_reference=? WHERE partner_id=?",
                      (credvault.encrypt(new_reference), partner_id))
        return self.payment_account(partner_id)

    # ---- счета за комиссию (commission_invoices) --------------------------- #
    def create_commission_invoice(self, iid: str, partner_id: str) -> dict | None:
        """Выставить счёт: собрать все accrued-строки ledger без счёта, привязать
        их к счёту и зафиксировать сумму. Нечего выставлять → None.
        Строки счёта замораживаются: сторно после выставления счёт не меняет
        (спорные заказы решаются void-ом счёта, не тихой правкой суммы)."""
        with self._lock, self._conn() as c:
            rows = c.execute(
                """SELECT id, commission_minor, created_at FROM commission_ledger
                   WHERE partner_id=? AND status='accrued' AND invoice_id IS NULL
                   ORDER BY created_at""", (partner_id,)).fetchall()
            if not rows:
                return None
            total = sum(r["commission_minor"] for r in rows)
            c.execute(
                """INSERT INTO commission_invoices(id,partner_id,total_minor,entries_count,
                   period_from,period_to,status,created_at)
                   VALUES(?,?,?,?,?,?,'open',?)""",
                (iid, partner_id, total, len(rows),
                 rows[0]["created_at"], rows[-1]["created_at"], _now_iso()))
            ids = [r["id"] for r in rows]
            c.executemany("UPDATE commission_ledger SET invoice_id=? WHERE id=?",
                          [(iid, x) for x in ids])
        return self.commission_invoice(iid)

    def commission_invoice(self, iid: str) -> dict | None:
        with self._lock, self._conn() as c:
            r = c.execute("SELECT * FROM commission_invoices WHERE id=?", (iid,)).fetchone()
        return dict(r) if r else None

    def commission_invoices(self, partner_id: str | None = None) -> list[dict]:
        with self._lock, self._conn() as c:
            if partner_id:
                rows = c.execute(
                    "SELECT * FROM commission_invoices WHERE partner_id=? ORDER BY created_at DESC",
                    (partner_id,)).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM commission_invoices ORDER BY created_at DESC").fetchall()
        return [dict(r) for r in rows]

    def set_invoice_status(self, iid: str, status: str) -> dict | None:
        """paid — партнёр оплатил; void — счёт аннулирован (строки возвращаются
        в пул невыставленных и попадут в следующий счёт)."""
        if status not in {"paid", "void"}:
            return None
        with self._lock, self._conn() as c:
            cur = c.execute(
                "UPDATE commission_invoices SET status=?, paid_at=? WHERE id=? AND status='open'",
                (status, _now_iso() if status == "paid" else None, iid))
            if not getattr(cur, "rowcount", 0):
                return None
            if status == "void":
                c.execute("UPDATE commission_ledger SET invoice_id=NULL WHERE invoice_id=?",
                          (iid,))
        return self.commission_invoice(iid)
