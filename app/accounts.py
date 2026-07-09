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
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from collections import deque

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi import Request as HttpRequest
from pydantic import BaseModel, field_validator

_DB = Path(__file__).parent.parent / "spasibox.db"
_SECRET = os.getenv("YUMMY_SECRET_KEY", "dev-only-secret-change-in-prod")
_PBKDF2_ROUNDS = 200_000
_TOKEN_TTL = 7 * 24 * 3600  # 7 дней
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter(tags=["Accounts"])
audit = logging.getLogger("yummy.audit")  # аудит-лог входов/регистраций (без паролей)

# Rate limit регистрации/входа: не более 6 попыток / мин с IP (анти-перебор).
_AUTH_MAX, _AUTH_WINDOW = 6, 60.0
_auth_hits: dict[str, deque[float]] = {}


def auth_rate_limit(req: HttpRequest) -> None:
    ip = req.client.host if req.client else "?"
    now = time.monotonic()
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


def create_token(sub: str, role: str, ttl: int = _TOKEN_TTL) -> str:
    header = _b64u(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64u(json.dumps({"sub": sub, "role": role, "exp": int(time.time()) + ttl}).encode())
    signing = f"{header}.{payload}".encode()
    sig = _b64u(hmac.new(_SECRET.encode(), signing, hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


def decode_token(token: str) -> dict:
    """Проверяет подпись и срок; бросает ValueError при любой проблеме."""
    try:
        header, payload, sig = token.split(".")
    except ValueError as exc:
        raise ValueError("некорректный токен") from exc
    expected = _b64u(hmac.new(_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        raise ValueError("подпись токена неверна")
    data = json.loads(_b64u_dec(payload))
    if data.get("exp", 0) < time.time():
        raise ValueError("токен истёк")
    return data


# --------------------------------------------------------------------------- #
#  Хранилище пользователей (та же SQLite-БД)
# --------------------------------------------------------------------------- #
class Accounts:
    def __init__(self, path: Path = _DB) -> None:
        self._path = path
        self._lock = threading.RLock()
        with self._lock, self._conn() as c:
            c.execute(
                """CREATE TABLE IF NOT EXISTS users(
                    id TEXT PRIMARY KEY, email TEXT UNIQUE, pw_hash TEXT, role TEXT,
                    brand_name TEXT, address TEXT, is_active INTEGER DEFAULT 1, created_at TEXT)"""
            )

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path)
        c.row_factory = sqlite3.Row
        return c

    def by_email(self, email: str) -> sqlite3.Row | None:
        with self._lock, self._conn() as c:
            return c.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()

    def by_id(self, uid: str) -> sqlite3.Row | None:
        with self._lock, self._conn() as c:
            return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

    def create(self, email: str, pw_hash: str, role: str,
               brand_name: str | None, address: str | None) -> str:
        uid = uuid.uuid4().hex
        with self._lock, self._conn() as c:
            c.execute(
                "INSERT INTO users(id,email,pw_hash,role,brand_name,address,is_active,created_at)"
                " VALUES(?,?,?,?,?,?,1,?)",
                (uid, email.lower(), pw_hash, role, brand_name, address,
                 datetime.now(timezone.utc).isoformat()),
            )
        return uid


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


class AuthResult(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: PublicUser


def _public(row: sqlite3.Row) -> PublicUser:
    return PublicUser(id=row["id"], email=row["email"], role=row["role"], brand_name=row["brand_name"])


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
    brand = data.brand_name if data.role == "partner" else None
    addr = data.address if data.role == "partner" else None
    if data.role == "partner" and not (brand and brand.strip()):
        raise HTTPException(422, "Для заведения укажите название")
    uid = accounts.create(data.email, hash_password(data.password), data.role, brand, addr)
    row = accounts.by_id(uid)
    audit.info("register OK id=%s role=%s email=%s ip=%s", uid, data.role, data.email, _ip(request))
    return AuthResult(access_token=create_token(uid, data.role), user=_public(row))


@router.post("/auth/login", response_model=AuthResult, dependencies=[Depends(auth_rate_limit)])
def login(data: LoginInput, request: HttpRequest) -> AuthResult:
    row = accounts.by_email(data.email)
    # одинаковая ошибка для «нет такого email» и «неверный пароль» — не раскрываем, что есть
    if not row or not verify_password(data.password, row["pw_hash"]):
        audit.warning("login FAIL email=%s ip=%s", data.email, _ip(request))
        raise HTTPException(401, "Неверный email или пароль")
    if not row["is_active"]:
        raise HTTPException(403, "Аккаунт отключён")
    audit.info("login OK id=%s ip=%s", row["id"], _ip(request))
    return AuthResult(access_token=create_token(row["id"], row["role"]), user=_public(row))


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
    return _public(row)


@router.get("/auth/me", response_model=PublicUser)
def me(user: PublicUser = Depends(current_user)) -> PublicUser:
    return user
