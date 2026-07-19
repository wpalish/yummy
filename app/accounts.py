"""Регистрация/вход по email+паролю — «как положено», но без тяжёлых зависимостей.

Пароль не хранится в открытом виде: PBKDF2-HMAC-SHA256 с солью и 200k итераций
(stdlib hashlib). Сессия — JWT HS256, тоже на stdlib (hmac+base64url). Роли:
customer / partner (у партнёра — профиль заведения). Всё в том же SQLite-файле.

Секрет берётся из env YUMMY_SECRET_KEY; в деве есть дефолт (в проде задать свой).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from collections import deque

from . import database

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi import Request as HttpRequest
from pydantic import BaseModel, field_validator

_DB = Path(os.getenv("YUMMY_DB_PATH", str(Path(__file__).parent.parent / "spasibox.db")))
_DEFAULT_SECRET = "dev-only-secret-change-in-prod"  # nosec B105 — сентинел, прод с ним не стартует (assert_prod_config)
_SECRET = os.getenv("YUMMY_SECRET_KEY", _DEFAULT_SECRET)


def assert_prod_config() -> None:
    """Fail-fast на старте: прод-режим с dev-секретом = любые токены подделываемы."""
    if os.getenv("YUMMY_ENFORCE_AUTH", "").lower() in {"1", "true", "yes"} and _SECRET == _DEFAULT_SECRET:
        raise RuntimeError(
            "YUMMY_ENFORCE_AUTH=1 требует настоящий YUMMY_SECRET_KEY "
            "(python -c 'import secrets;print(secrets.token_hex(32))'; см. .env.example)"
        )
# Роли персонала внутри заведения (кто что может в партнёрке)
_STAFF_ROLES = ("owner", "manager", "cashier")

_PBKDF2_ROUNDS = 600_000        # OWASP-рекомендация для PBKDF2-SHA256; старые
                                 # хеши верифицируются по rounds из самой записи
_TOKEN_TTL = 15 * 60             # короткий access-токен (Sentinel-паттерн)
_REFRESH_TTL = 30 * 24 * 3600    # refresh — 30 дней, ротируется при каждом использовании
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter(tags=["Accounts"])
audit = logging.getLogger("yummy.audit")  # аудит-лог входов/регистраций (без паролей)

# Rate limit регистрации/входа: не более 6 попыток / мин с IP (анти-перебор).
_AUTH_MAX, _AUTH_WINDOW = 6, 60.0
_auth_hits: dict[str, deque[float]] = {}

# Login-jail по аккаунту (идея из xapax/security): N неудач подряд по одному
# email → временный блок, даже с верным паролем и с другого IP.
_JAIL_FAILS, _JAIL_SECONDS = 5, 600
_jail: dict[str, tuple[int, float]] = {}  # email -> (fails, locked_until_monotonic)


def _jail_check(email: str) -> None:
    fails, until = _jail.get(email, (0, 0.0))
    if until > time.monotonic():
        raise HTTPException(429, "Аккаунт временно заблокирован после неудачных попыток. Подождите 10 минут")


def _jail_fail(email: str) -> None:
    fails, _ = _jail.get(email, (0, 0.0))
    fails += 1
    until = time.monotonic() + _JAIL_SECONDS if fails >= _JAIL_FAILS else 0.0
    _jail[email] = (fails, until)


def _jail_reset(email: str) -> None:
    _jail.pop(email, None)


def _purge_hits(hits_map: dict, window: float) -> None:
    """Не даём карте лимитера расти бесконечно (память при массовых IP)."""
    if len(hits_map) < 4096:
        return
    now = time.monotonic()
    for key in [k for k, q in hits_map.items() if not q or now - q[-1] > window]:
        hits_map.pop(key, None)


def auth_rate_limit(req: HttpRequest) -> None:
    ip = req.client.host if req.client else "?"
    now = time.monotonic()
    _purge_hits(_auth_hits, _AUTH_WINDOW)
    hits = _auth_hits.setdefault(ip, deque())
    while hits and now - hits[0] > _AUTH_WINDOW:
        hits.popleft()
    if len(hits) >= _AUTH_MAX:
        raise HTTPException(429, "Слишком много попыток, подождите минуту")
    hits.append(now)


# --------------------------------------------------------------------------- #
#  Пароль: соль + PBKDF2, без внешних библиотек
# --------------------------------------------------------------------------- #
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${_PBKDF2_ROUNDS}${salt.hex()}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, rounds, salt_hex, hash_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


# --------------------------------------------------------------------------- #
#  JWT HS256 на stdlib (тот же алгоритм, что у настоящих JWT-библиотек)
# --------------------------------------------------------------------------- #
def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


_ISSUER = "yummy"  # строгая проверка издателя (паттерн из spring-security)


def create_token(sub: str, role: str, ttl: int = _TOKEN_TTL, ver: int = 0) -> str:
    header = _b64u(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64u(json.dumps(
        {"iss": _ISSUER, "sub": sub, "role": role, "ver": ver, "exp": int(time.time()) + ttl}
    ).encode())
    signing = f"{header}.{payload}".encode()
    sig = _b64u(hmac.new(_SECRET.encode(), signing, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict:
    """Проверяет подпись, издателя и срок; бросает ValueError при любой проблеме."""
    try:
        header, payload, sig = token.split(".")
    except ValueError as exc:
        raise ValueError("некорректный токен") from exc
    expected = _b64u(hmac.new(_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        raise ValueError("подпись токена неверна")
    data = json.loads(_b64u_dec(payload))
    if data.get("iss") != _ISSUER:
        raise ValueError("неверный издатель токена")
    if data.get("exp", 0) < time.time():
        raise ValueError("токен истёк")
    return data


# --------------------------------------------------------------------------- #
#  Хранилище пользователей (та же SQLite-БД)
# --------------------------------------------------------------------------- #
class Accounts:
    def __init__(self, path: Path = _DB) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)  # вложенный путь (напр. /var/data)
        self._lock = threading.RLock()
        with self._lock, self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS users(
                    id TEXT PRIMARY KEY, email TEXT UNIQUE, pw_hash TEXT, role TEXT,
                    brand_name TEXT, address TEXT, is_active INTEGER DEFAULT 1,
                    created_at TEXT, token_ver INTEGER DEFAULT 0,
                    partner_id TEXT, partner_role TEXT)"""
            )
            # Миграции колонок. CREATE TABLE IF NOT EXISTS не трогает уже
            # существующую таблицу — на живой БД (Supabase) колонки надо
            # доливать явно, иначе UPDATE ниже падает UndefinedColumn.
            if database.POSTGRES:
                for col, ddl in (("token_ver", "INTEGER DEFAULT 0"),
                                 ("partner_id", "TEXT"), ("partner_role", "TEXT")):
                    c.execute(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {ddl}")
            else:
                cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
                if "token_ver" not in cols:
                    c.execute("ALTER TABLE users ADD COLUMN token_ver INTEGER DEFAULT 0")
                if "partner_id" not in cols:
                    c.execute("ALTER TABLE users ADD COLUMN partner_id TEXT")
                if "partner_role" not in cols:
                    c.execute("ALTER TABLE users ADD COLUMN partner_role TEXT")
            # существующие партнёры — владельцы своего заведения
            c.execute("UPDATE users SET partner_role='owner' "
                      "WHERE role='partner' AND partner_role IS NULL")
            c.execute(
                """CREATE TABLE IF NOT EXISTS refresh_tokens(
                    token_hash TEXT PRIMARY KEY, user_id TEXT,
                    expires_at INTEGER, revoked INTEGER DEFAULT 0)"""
            )
            c.execute("CREATE INDEX IF NOT EXISTS ix_refresh_user ON refresh_tokens(user_id)")
            # Приглашения персонала: доступ к партнёрке/админке ТОЛЬКО по инвайту от
            # админа. В БД — SHA-256-хеш токена (как у refresh), не сырое значение.
            c.execute(
                """CREATE TABLE IF NOT EXISTS staff_invitations(
                    token_hash TEXT PRIMARY KEY, email TEXT, partner_id TEXT,
                    partner_role TEXT, brand_name TEXT, address TEXT,
                    expires_at INTEGER, used_at INTEGER,
                    invited_by TEXT, created_at INTEGER)"""
            )
            c.execute("CREATE INDEX IF NOT EXISTS ix_invites_email "
                      "ON staff_invitations(email,used_at)")

    @contextmanager
    def _conn(self):
        if database.POSTGRES:
            with database.connection() as c:
                yield c
            return
        c = sqlite3.connect(self._path, timeout=5.0)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000")
        try:
            with c:
                yield c
        finally:
            c.close()

    def by_email(self, email: str) -> sqlite3.Row | None:
        with self._lock, self._conn() as c:
            return c.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()

    def by_id(self, uid: str) -> sqlite3.Row | None:
        with self._lock, self._conn() as c:
            return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

    # ---- refresh-токены: случайные, в БД только SHA-256-хеш, ротация ---- #
    @staticmethod
    def _rt_hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    def issue_refresh(self, user_id: str) -> str:
        raw = secrets.token_urlsafe(32)
        with self._lock, self._conn() as c:
            c.execute("INSERT INTO refresh_tokens(token_hash,user_id,expires_at) VALUES(?,?,?)",
                      (self._rt_hash(raw), user_id, int(time.time()) + _REFRESH_TTL))
        return raw

    def rotate_refresh(self, raw: str) -> str | None:
        """Валиден → отзываем использованный и выдаём новый; иначе None."""
        h = self._rt_hash(raw)
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM refresh_tokens WHERE token_hash=?", (h,)).fetchone()
            if not row or row["revoked"] or row["expires_at"] < time.time():
                return None
            c.execute("UPDATE refresh_tokens SET revoked=1 WHERE token_hash=?", (h,))
        return row["user_id"]

    def revoke_all_refresh(self, user_id: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (user_id,))

    # ---- админ: список, блокировка, отзыв сессий ------------------------- #
    def list_users(self, limit: int = 200) -> list[sqlite3.Row]:
        with self._lock, self._conn() as c:
            return c.execute(
                "SELECT id,email,role,brand_name,partner_id,partner_role,is_active,created_at"
                " FROM users ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()

    def set_active(self, user_id: str, active: bool) -> bool:
        """Блокировка/разблокировка. При блокировке рвём все сессии: поднимаем
        token_ver (старые access-токены становятся невалидными) и гасим refresh."""
        with self._lock, self._conn() as c:
            cur = c.execute("UPDATE users SET is_active=? WHERE id=?",
                            (1 if active else 0, user_id))
            if not getattr(cur, "rowcount", 0):
                return False
            if not active:
                c.execute("UPDATE users SET token_ver=COALESCE(token_ver,0)+1 WHERE id=?",
                          (user_id,))
                c.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (user_id,))
        return True

    def revoke_sessions(self, user_id: str) -> bool:
        """Разлогинить со всех устройств, не блокируя аккаунт."""
        with self._lock, self._conn() as c:
            cur = c.execute("UPDATE users SET token_ver=COALESCE(token_ver,0)+1 WHERE id=?",
                            (user_id,))
            c.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (user_id,))
            return bool(getattr(cur, "rowcount", 0))

    def partner_staff(self, partner_id: str) -> list[sqlite3.Row]:
        """Персонал заведения — для кабинета владельца (владелец сверху, потом
        менеджеры, потом кассиры; внутри группы — по дате)."""
        with self._lock, self._conn() as c:
            return c.execute(
                "SELECT id,email,role,partner_id,partner_role,is_active,created_at"
                " FROM users WHERE partner_id=? ORDER BY"
                " CASE partner_role WHEN 'owner' THEN 0 WHEN 'manager' THEN 1"
                " ELSE 2 END, created_at", (partner_id,)).fetchall()

    def set_partner_role(self, user_id: str, partner_id: str, new_role: str) -> bool:
        """Сменить роль сотрудника ВНУТРИ его заведения (manager<->cashier).
        Владельцем через этот путь не делаем и чужой персонал не трогаем —
        WHERE привязывает и к заведению, и к нессотрудничьей роли."""
        if new_role not in {"manager", "cashier"}:
            return False
        with self._lock, self._conn() as c:
            cur = c.execute(
                "UPDATE users SET partner_role=? WHERE id=? AND partner_id=?"
                " AND partner_role IN ('manager','cashier')",
                (new_role, user_id, partner_id))
            return bool(getattr(cur, "rowcount", 0))

    def create(self, email: str, pw_hash: str, role: str,
               brand_name: str | None, address: str | None,
               partner_id: str | None = None, partner_role: str | None = None) -> str:
        uid = uuid.uuid4().hex
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO users(id,email,pw_hash,role,brand_name,address,is_active,"
                "created_at,partner_id,partner_role) VALUES(?,?,?,?,?,?,1,?,?,?)",
                (uid, email.lower(), pw_hash, role, brand_name, address,
                 datetime.now(timezone.utc).isoformat(), partner_id, partner_role),
            )
        return uid

    # ---- приглашения персонала (доступ к партнёрке/админке только по инвайту) ---- #
    def issue_staff_invitation(self, *, email: str, partner_id: str | None,
                               partner_role: str, invited_by: str,
                               brand_name: str = "", address: str = "",
                               ttl: int = 7 * 86400) -> str:
        """Создать одноразовый инвайт, вернуть СЫРОЙ токен (в БД — только хеш).
        Прошлые неиспользованные инвайты на этот email гасятся."""
        if partner_role not in _STAFF_ROLES:
            raise ValueError("неизвестная роль персонала")
        raw = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._lock, self._conn() as c:
            c.execute("UPDATE staff_invitations SET used_at=? WHERE email=? AND used_at IS NULL",
                      (now, email.lower()))
            c.execute(
                "INSERT INTO staff_invitations(token_hash,email,partner_id,partner_role,"
                "brand_name,address,expires_at,used_at,invited_by,created_at)"
                " VALUES(?,?,?,?,?,?,?,NULL,?,?)",
                (self._rt_hash(raw), email.lower(), partner_id, partner_role,
                 brand_name, address, now + ttl, invited_by, now),
            )
        return raw

    def peek_invitation(self, raw: str):
        """Прочитать валидный инвайт, НЕ погашая (для превью формы регистрации)."""
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM staff_invitations WHERE token_hash=?",
                            (self._rt_hash(raw),)).fetchone()
        if not row or row["used_at"] is not None or row["expires_at"] < time.time():
            return None
        return row

    def claim_invitation(self, raw: str):
        """Атомарно погасить инвайт. Возвращает ряд или None (использован/просрочен)."""
        h, now = self._rt_hash(raw), int(time.time())
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM staff_invitations WHERE token_hash=?", (h,)).fetchone()
            if not row or row["used_at"] is not None or row["expires_at"] < now:
                return None
            c.execute("UPDATE staff_invitations SET used_at=? WHERE token_hash=? AND used_at IS NULL",
                      (now, h))
        return row


accounts = Accounts()


# --------------------------------------------------------------------------- #
#  Схемы (пароль-хеш НИКОГДА не попадает в ответ)
# --------------------------------------------------------------------------- #
class RegisterInput(BaseModel):
    email: str
    password: str
    role: Literal["customer", "partner"] = "customer"
    brand_name: str | None = None
    address: str | None = None

    @field_validator("email")
    @classmethod
    def _email_ok(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("некорректный email")
        return v.strip().lower()

    @field_validator("password")
    @classmethod
    def _password_strong(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("пароль должен быть не короче 8 символов")
        if not any(ch.isdigit() for ch in v) or not any(ch.isalpha() for ch in v):
            raise ValueError("пароль должен содержать буквы и цифры")
        return v


class LoginInput(BaseModel):
    email: str
    password: str


class PublicUser(BaseModel):
    id: str
    email: str
    role: str
    brand_name: str | None = None
    partner_id: str | None = None
    partner_role: str | None = None   # owner | manager | cashier (у персонала)


class StaffInvitationCreate(BaseModel):
    """Админ приглашает персонал/владельца заведения."""

    email: str
    partner_role: Literal["owner", "manager", "cashier"] = "owner"
    partner_id: str | None = None      # для manager/cashier — в какое заведение
    brand_name: str = ""               # для owner — новое заведение
    address: str = ""

    @field_validator("email")
    @classmethod
    def _email_ok(cls, v: str) -> str:
        if not _EMAIL_RE.match(v.strip()):
            raise ValueError("некорректный email")
        return v.strip().lower()


class StaffRoleUpdate(BaseModel):
    """Владелец меняет роль сотрудника внутри заведения (не в owner)."""

    partner_role: Literal["manager", "cashier"]


class StaffInvitationResult(BaseModel):
    invite_url: str
    expires_in_days: int = 7


class InviteAcceptInput(BaseModel):
    token: str
    password: str
    name: str = ""

    @field_validator("password")
    @classmethod
    def _password_strong(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("пароль должен быть не короче 8 символов")
        if not any(ch.isdigit() for ch in v) or not any(ch.isalpha() for ch in v):
            raise ValueError("пароль должен содержать буквы и цифры")
        return v


class InvitePreview(BaseModel):
    email: str
    partner_role: str
    brand_name: str = ""


class AuthResult(BaseModel):
    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    user: PublicUser


def _public(row: sqlite3.Row) -> PublicUser:
    keys = row.keys()
    return PublicUser(id=row["id"], email=row["email"], role=row["role"],
                      brand_name=row["brand_name"],
                      partner_id=row["partner_id"] if "partner_id" in keys else None,
                      partner_role=row["partner_role"] if "partner_role" in keys else None)


# --------------------------------------------------------------------------- #
#  Эндпоинты
# --------------------------------------------------------------------------- #
def _ip(req: HttpRequest) -> str:
    return req.client.host if req and req.client else "?"


@router.post("/auth/register", response_model=AuthResult, status_code=201,
             dependencies=[Depends(auth_rate_limit)])
def register(data: RegisterInput, request: HttpRequest) -> AuthResult:
    if accounts.by_email(data.email):
        audit.info("register DENIED (email занят) email=%s ip=%s", data.email, _ip(request))
        raise HTTPException(409, "Email уже зарегистрирован")
    # Партнёром/персоналом становятся ТОЛЬКО по инвайту от админа (/auth/accept-invite).
    # Публичная регистрация — исключительно покупатель, иначе любой получил бы
    # доступ к партнёрке. Админ — по allowlist почт (YUMMY_ADMIN_EMAILS).
    if data.role == "partner":
        audit.info("register DENIED (partner без инвайта) email=%s ip=%s",
                   data.email, _ip(request))
        raise HTTPException(403, "Заведения подключаются по приглашению — напишите нам")
    role = "admin" if data.email in _ADMIN_EMAILS else "customer"
    uid = accounts.create(data.email, hash_password(data.password), role, None, None)
    row = accounts.by_id(uid)
    audit.info("register OK id=%s role=%s email=%s ip=%s", uid, role, data.email, _ip(request))
    return AuthResult(access_token=create_token(uid, role, ver=_row_token_ver(row)),
                      refresh_token=accounts.issue_refresh(uid), user=_public(row))


@router.post("/auth/login", response_model=AuthResult, dependencies=[Depends(auth_rate_limit)])
def login(data: LoginInput, request: HttpRequest) -> AuthResult:
    email = data.email.strip().lower()
    _jail_check(email)
    row = accounts.by_email(email)
    # одинаковая ошибка для «нет такого email» и «неверный пароль» — не раскрываем, что есть
    if not row or not verify_password(data.password, row["pw_hash"]):
        _jail_fail(email)
        audit.warning("login FAIL email=%s ip=%s", email, _ip(request))
        raise HTTPException(401, "Неверный email или пароль")
    if not row["is_active"]:
        raise HTTPException(403, "Аккаунт отключён")
    _jail_reset(email)
    audit.info("login OK id=%s ip=%s", row["id"], _ip(request))
    return AuthResult(access_token=create_token(row["id"], row["role"], ver=_row_token_ver(row)),
                      refresh_token=accounts.issue_refresh(row["id"]), user=_public(row))


class RefreshInput(BaseModel):
    refresh_token: str


@router.post("/auth/refresh", response_model=AuthResult, dependencies=[Depends(auth_rate_limit)])
def refresh(data: RefreshInput, request: HttpRequest) -> AuthResult:
    """Обновить короткий access-токен. Refresh ротируется: старый сгорает."""
    uid = accounts.rotate_refresh(data.refresh_token)
    row = accounts.by_id(uid) if uid else None
    if not row or not row["is_active"]:
        audit.warning("refresh FAIL ip=%s", _ip(request))
        raise HTTPException(401, "Refresh-токен недействителен, войдите заново")
    return AuthResult(access_token=create_token(row["id"], row["role"], ver=_row_token_ver(row)),
                      refresh_token=accounts.issue_refresh(row["id"]), user=_public(row))


# /auth/logout-all — ниже, после определения current_user


def _row_token_ver(row) -> int:
    try:
        return int(row["token_ver"] or 0)
    except (KeyError, IndexError, TypeError):
        return 0


def optional_user(authorization: str | None = Header(default=None)) -> PublicUser | None:
    """Мягкая авторизация: токен есть и валиден → юзер, иначе None (гость)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    try:
        payload = decode_token(authorization.split(" ", 1)[1])
        row = accounts.by_id(payload["sub"])
        if not row or payload.get("ver", 0) != _row_token_ver(row):
            return None
        return _public(row)
    except ValueError:
        return None


def current_user(authorization: str | None = Header(default=None)) -> PublicUser:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Нужен Bearer-токен")
    try:
        payload = decode_token(authorization.split(" ", 1)[1])
    except ValueError as exc:
        raise HTTPException(401, f"Токен: {exc}") from exc
    row = accounts.by_id(payload["sub"])
    if not row:
        raise HTTPException(401, "Пользователь не найден")
    if payload.get("ver", 0) != _row_token_ver(row):
        # пароль менялся после выпуска токена — все старые сессии отозваны
        raise HTTPException(401, "Сессия недействительна, войдите заново")
    if not row["is_active"]:            # заблокирован админом — токен бесполезен
        raise HTTPException(403, "Аккаунт отключён")
    return _public(row)


@router.get("/auth/me", response_model=PublicUser)
def me(user: PublicUser = Depends(current_user)) -> PublicUser:
    return user


@router.post("/auth/logout-all")
def logout_all(request: HttpRequest, user: PublicUser = Depends(current_user)) -> dict:
    """Выйти со всех устройств: отзывает все access- и refresh-токены."""
    with accounts._lock, accounts._conn() as c:
        c.execute("UPDATE users SET token_ver=COALESCE(token_ver,0)+1 WHERE id=?", (user.id,))
    accounts.revoke_all_refresh(user.id)
    audit.info("logout-all id=%s ip=%s", user.id, _ip(request))
    return {"status": "ok"}


class ChangePasswordInput(BaseModel):
    old_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def _strong(cls, v: str) -> str:
        return RegisterInput._password_strong(v)


@router.post("/auth/change-password", dependencies=[Depends(auth_rate_limit)])
def change_password(data: ChangePasswordInput,
                    request: HttpRequest,
                    user: PublicUser = Depends(current_user)) -> dict:
    row = accounts.by_id(user.id)
    if not row or not verify_password(data.old_password, row["pw_hash"]):
        audit.warning("change-password FAIL id=%s ip=%s", user.id, _ip(request))
        raise HTTPException(401, "Текущий пароль неверен")
    with accounts._lock, accounts._conn() as c:
        # token_ver+1 отзывает ВСЕ ранее выданные токены (украденный JWT умирает)
        c.execute("UPDATE users SET pw_hash=?, token_ver=COALESCE(token_ver,0)+1 WHERE id=?",
                  (hash_password(data.new_password), user.id))
    accounts.revoke_all_refresh(user.id)
    row = accounts.by_id(user.id)
    audit.info("change-password OK id=%s ip=%s (сессии отозваны)", user.id, _ip(request))
    # свежая пара — чтобы текущее устройство осталось залогиненным
    return {"status": "ok",
            "access_token": create_token(user.id, row["role"], ver=_row_token_ver(row)),
            "refresh_token": accounts.issue_refresh(user.id)}


# --------------------------------------------------------------------------- #
#  Ролевой доступ (из API-Security-Checklist: «все эндпоинты за аутентификацией»)
#  Включается флагом YUMMY_ENFORCE_AUTH=1 — так прод защищён, а демо (без флага)
#  продолжает работать без токенов.
# --------------------------------------------------------------------------- #
_ENFORCE = os.getenv("YUMMY_ENFORCE_AUTH", "").lower() in {"1", "true", "yes"}

# Владельцы: email из этого списка при регистрации получают роль admin.
_ADMIN_EMAILS = {e.strip().lower() for e in os.getenv("YUMMY_ADMIN_EMAILS", "").split(",") if e.strip()}


def require_role(*roles: str):
    """Dependency-фабрика: требует валидный JWT нужной роли (когда включено)."""
    def _dep(authorization: str | None = Header(default=None)) -> PublicUser | None:
        if not _ENFORCE:
            return None  # демо-режим: доступ открыт (как раньше)
        user = current_user(authorization)  # 401, если токена нет/невалиден
        if roles and user.role not in roles:
            raise HTTPException(403, "Недостаточно прав")
        return user
    return _dep
