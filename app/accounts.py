"""Регистрация/вход по email+паролю — «как положено», но без тяжёлых зависимостей.

Пароль не хранится в открытом виде: Argon2id с уникальной солью и memory-hard
параметрами; legacy PBKDF2 мигрирует после входа. Сессия — JWT HS256. Роли:
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
import struct
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from collections import deque

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi import Request as HttpRequest
from pydantic import BaseModel, Field, field_validator

_DB = Path(os.getenv("YUMMY_DB_PATH", str(Path(__file__).parent.parent / "spasibox.db")))
# Намеренный dev-сентинел; assert_prod_config не даст запустить его в production.
_DEFAULT_SECRET = "dev-only-secret-change-in-prod"  # nosec B105
_SECRET = os.getenv("YUMMY_SECRET_KEY", _DEFAULT_SECRET)
_DATA_SECRET = os.getenv("YUMMY_DATA_KEY", "")


def assert_prod_config() -> None:
    """Fail-fast на старте: прод-режим с dev-секретом = любые токены подделываемы."""
    production = os.getenv("YUMMY_ENV", "").lower() == "production"
    # Backward compatibility для уже развёрнутых инстансов; доступ к private API
    # теперь защищён всегда и от этого legacy-флага не зависит.
    production = production or os.getenv("YUMMY_ENFORCE_AUTH", "").lower() in {"1", "true", "yes"}
    if production and (_SECRET == _DEFAULT_SECRET or len(_SECRET.encode()) < 32):
        raise RuntimeError(
            "YUMMY_ENV=production требует YUMMY_SECRET_KEY минимум 32 байта "
            "(python -c 'import secrets;print(secrets.token_hex(32))'; см. .env.example)"
        )
    if production and (len(_DATA_SECRET.encode()) < 32 or _DATA_SECRET == _SECRET):
        raise RuntimeError(
            "production требует отдельный YUMMY_DATA_KEY минимум 32 байта для MFA secrets"
        )
_TOKEN_TTL = 15 * 60             # короткий access-токен (Sentinel-паттерн)
_REFRESH_TTL = 30 * 24 * 3600    # refresh — 30 дней, ротируется при каждом использовании
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_TERMS_VERSION = "2026-07-14"
_PRODUCTION = (
    os.getenv("YUMMY_ENV", "").lower() == "production"
    or os.getenv("YUMMY_ENFORCE_AUTH", "").lower() in {"1", "true", "yes"}
)
_ACCESS_COOKIE = "__Host-yummy_access" if _PRODUCTION else "yummy_access"
_REFRESH_COOKIE = "__Secure-yummy_refresh" if _PRODUCTION else "yummy_refresh"
_CSRF_COOKIE = "__Host-yummy_csrf" if _PRODUCTION else "yummy_csrf"

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
#  Пароль: Argon2id; legacy PBKDF2 прозрачно мигрирует после успешного входа.
#  64 MiB / 3 прохода / 4 lanes — намеренно memory-hard против GPU-перебора.
# --------------------------------------------------------------------------- #
_ARGON2 = PasswordHasher(time_cost=3, memory_cost=65_536, parallelism=4,
                         hash_len=32, salt_len=16)


def hash_password(password: str) -> str:
    return _ARGON2.hash(password)


def verify_password(password: str, stored: str) -> bool:
    if stored.startswith("$argon2"):
        try:
            return _ARGON2.verify(stored, password)
        except (InvalidHashError, VerificationError, VerifyMismatchError):
            return False
    # Backward compatibility: не разлогиниваем пользователей со старыми хешами.
    try:
        algorithm, rounds, salt_hex, hash_hex = stored.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(rounds)
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk.hex(), hash_hex)


def password_needs_rehash(stored: str) -> bool:
    if not stored.startswith("$argon2"):
        return True
    try:
        return _ARGON2.check_needs_rehash(stored)
    except InvalidHashError:
        return True


# --------------------------------------------------------------------------- #
#  MFA: AES-256-GCM encrypted TOTP seed + replay-safe RFC 6238 verification.
# --------------------------------------------------------------------------- #
_MFA_KEY = hashlib.sha256((_DATA_SECRET or f"dev:{_SECRET}:mfa").encode()).digest()
_MFA_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def encrypt_mfa_secret(secret: str, user_id: str) -> str:
    nonce = secrets.token_bytes(12)
    encrypted = AESGCM(_MFA_KEY).encrypt(nonce, secret.encode(), user_id.encode())
    return "v1:" + base64.urlsafe_b64encode(nonce + encrypted).decode()


def decrypt_mfa_secret(value: str, user_id: str) -> str:
    if not value.startswith("v1:"):
        raise ValueError("неизвестная версия MFA secret")
    raw = base64.urlsafe_b64decode(value[3:])
    return AESGCM(_MFA_KEY).decrypt(raw[:12], raw[12:], user_id.encode()).decode()


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def totp_code(secret: str, counter: int) -> str:
    padded = secret + "=" * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def _recovery_hash(user_id: str, code: str) -> str:
    normalized = code.replace("-", "").strip().upper()
    return hmac.new(_MFA_KEY, f"{user_id}:{normalized}".encode(), hashlib.sha256).hexdigest()


def generate_recovery_codes(count: int = 10) -> list[str]:
    return ["-".join(
        "".join(secrets.choice(_MFA_ALPHABET) for _ in range(4)) for _ in range(3)
    ) for _ in range(count)]


def totp_uri(secret: str, email: str) -> str:
    label = quote(f"Yummy:{email}", safe="")
    return f"otpauth://totp/{label}?secret={secret}&issuer=Yummy&algorithm=SHA1&digits=6&period=30"


# --------------------------------------------------------------------------- #
#  JWT HS256 на stdlib (тот же алгоритм, что у настоящих JWT-библиотек)
# --------------------------------------------------------------------------- #
def _b64u(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


_ISSUER = "yummy"
_AUDIENCE = "yummy-api"


def create_token(sub: str, role: str, ttl: int = _TOKEN_TTL, ver: int = 0,
                 *, mfa_verified: bool = False) -> str:
    header = _b64u(b'{"alg":"HS256","typ":"JWT"}')
    now = int(time.time())
    payload = _b64u(json.dumps({
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "sub": sub,
        "role": role,
        "ver": ver,
        "amr": ["pwd", "mfa"] if mfa_verified else ["pwd"],
        "iat": now,
        "nbf": now - 1,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }, separators=(",", ":")).encode())
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
    try:
        token_header = json.loads(_b64u_dec(header))
        data = json.loads(_b64u_dec(payload))
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("некорректный токен") from exc
    if token_header.get("alg") != "HS256" or token_header.get("typ") != "JWT":
        raise ValueError("неподдерживаемый алгоритм токена")
    now = time.time()
    if data.get("iss") != _ISSUER:
        raise ValueError("неверный издатель токена")
    if data.get("aud") != _AUDIENCE:
        raise ValueError("неверная аудитория токена")
    if not isinstance(data.get("sub"), str) or not data["sub"]:
        raise ValueError("в токене отсутствует subject")
    if not isinstance(data.get("exp"), (int, float)) or data["exp"] <= now:
        raise ValueError("токен истёк")
    if not isinstance(data.get("iat"), (int, float)) or data["iat"] > now + 60:
        raise ValueError("некорректное время выпуска токена")
    if not isinstance(data.get("nbf"), (int, float)) or data["nbf"] > now:
        raise ValueError("токен ещё не активен")
    if not isinstance(data.get("jti"), str) or not data["jti"]:
        raise ValueError("в токене отсутствует jti")
    if not isinstance(data.get("amr"), list) or not all(isinstance(x, str) for x in data["amr"]):
        raise ValueError("в токене отсутствует amr")
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
                    id TEXT PRIMARY KEY, email TEXT UNIQUE, email_verified INTEGER DEFAULT 0,
                    pw_hash TEXT, role TEXT, brand_name TEXT, address TEXT, district TEXT,
                    partner_id TEXT, partner_status TEXT,
                    is_active INTEGER DEFAULT 1, created_at TEXT,
                    token_ver INTEGER DEFAULT 0,
                    terms_accepted_at TEXT, terms_version TEXT,
                    mfa_secret TEXT, mfa_enabled INTEGER DEFAULT 0,
                    mfa_last_counter INTEGER DEFAULT -1)"""
            )
            # Аддитивные миграции: старые SQLite-файлы обновляются без простоя и
            # без потери аккаунтов. Legacy partner получает собственный tenant id.
            cols = {r[1] for r in c.execute("PRAGMA table_info(users)").fetchall()}
            if "token_ver" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN token_ver INTEGER DEFAULT 0")
            if "email_verified" not in cols:
                # Legacy accounts remain usable; only new public registrations start unverified.
                c.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 1")
            if "mfa_secret" not in cols:
                c.execute("ALTER TABLE users ADD COLUMN mfa_secret TEXT")
            migrations = {
                "district": "TEXT",
                "partner_id": "TEXT",
                "partner_status": "TEXT",
                "terms_accepted_at": "TEXT",
                "terms_version": "TEXT",
                "mfa_enabled": "INTEGER DEFAULT 0",
                "mfa_last_counter": "INTEGER DEFAULT -1",
            }
            for name, ddl in migrations.items():
                if name not in cols:
                    c.execute(f"ALTER TABLE users ADD COLUMN {name} {ddl}")
            c.execute(
                "UPDATE users SET partner_id=id "
                "WHERE role='partner' AND (partner_id IS NULL OR partner_id='')"
            )
            c.execute(
                "UPDATE users SET partner_status='pending' "
                "WHERE role='partner' AND (partner_status IS NULL OR partner_status='')"
            )
            c.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_users_partner ON users(partner_id) "
                      "WHERE partner_id IS NOT NULL")
            c.execute(
                """CREATE TABLE IF NOT EXISTS refresh_tokens(
                    token_hash TEXT PRIMARY KEY, user_id TEXT,
                    family_id TEXT, expires_at INTEGER,
                    revoked INTEGER DEFAULT 0, used_at INTEGER,
                    mfa_verified INTEGER DEFAULT 0)"""
            )
            refresh_cols = {
                r[1] for r in c.execute("PRAGMA table_info(refresh_tokens)").fetchall()
            }
            if "family_id" not in refresh_cols:
                c.execute("ALTER TABLE refresh_tokens ADD COLUMN family_id TEXT")
            if "used_at" not in refresh_cols:
                c.execute("ALTER TABLE refresh_tokens ADD COLUMN used_at INTEGER")
            if "mfa_verified" not in refresh_cols:
                c.execute("ALTER TABLE refresh_tokens ADD COLUMN mfa_verified INTEGER DEFAULT 0")
            c.execute("""CREATE TABLE IF NOT EXISTS mfa_recovery_codes(
                user_id TEXT, code_hash TEXT PRIMARY KEY, used_at INTEGER)""")
            c.execute("""CREATE TABLE IF NOT EXISTS action_tokens(
                token_hash TEXT PRIMARY KEY, user_id TEXT, purpose TEXT,
                expires_at INTEGER, used_at INTEGER, created_at INTEGER)""")
            c.execute("CREATE INDEX IF NOT EXISTS ix_action_user ON action_tokens(user_id,purpose)")
            c.execute("CREATE INDEX IF NOT EXISTS ix_refresh_user ON refresh_tokens(user_id)")
            c.execute("CREATE INDEX IF NOT EXISTS ix_refresh_family ON refresh_tokens(family_id)")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self._path, timeout=5.0)
        c.row_factory = sqlite3.Row
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA busy_timeout=5000")
        return c

    def by_email(self, email: str) -> sqlite3.Row | None:
        with self._lock, self._conn() as c:
            return c.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()

    def by_id(self, uid: str) -> sqlite3.Row | None:
        with self._lock, self._conn() as c:
            return c.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()

    # ---- MFA setup/verification ----------------------------------------- #
    def configure_mfa(self, user_id: str, email: str) -> dict:
        secret = generate_totp_secret()
        codes = generate_recovery_codes()
        encrypted = encrypt_mfa_secret(secret, user_id)
        with self._lock, self._conn() as c:
            row = c.execute("SELECT 1 FROM users WHERE id=?", (user_id,)).fetchone()
            if not row:
                raise ValueError("пользователь не найден")
            c.execute(
                """UPDATE users SET mfa_secret=?,mfa_enabled=1,mfa_last_counter=-1,
                   token_ver=COALESCE(token_ver,0)+1 WHERE id=?""",
                (encrypted, user_id),
            )
            c.execute("DELETE FROM mfa_recovery_codes WHERE user_id=?", (user_id,))
            c.executemany(
                "INSERT INTO mfa_recovery_codes(user_id,code_hash) VALUES(?,?)",
                [(user_id, _recovery_hash(user_id, code)) for code in codes],
            )
        self.revoke_all_refresh(user_id)
        audit.warning("mfa RESET id=%s", user_id)
        return {"secret": secret, "uri": totp_uri(secret, email), "recovery_codes": codes}

    def consume_mfa(self, user_id: str, code: str, now: int | None = None) -> str | None:
        normalized = code.replace(" ", "").strip().upper()
        current = (now if now is not None else int(time.time())) // 30
        with self._lock, self._conn() as c:
            row = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
            if not row or not row["mfa_enabled"] or not row["mfa_secret"]:
                return None
            if normalized.isdigit() and len(normalized) == 6:
                try:
                    secret = decrypt_mfa_secret(row["mfa_secret"], user_id)
                except (ValueError, TypeError):
                    audit.error("mfa DECRYPT-FAIL id=%s", user_id)
                    return None
                for counter in (current - 1, current, current + 1):
                    if counter <= int(row["mfa_last_counter"] or -1):
                        continue
                    if hmac.compare_digest(totp_code(secret, counter), normalized):
                        updated = c.execute(
                            """UPDATE users SET mfa_last_counter=?
                               WHERE id=? AND mfa_last_counter<?""",
                            (counter, user_id, counter),
                        )
                        return "totp" if updated.rowcount == 1 else None
                return None
            code_hash = _recovery_hash(user_id, normalized)
            used = c.execute(
                """UPDATE mfa_recovery_codes SET used_at=?
                   WHERE user_id=? AND code_hash=? AND used_at IS NULL""",
                (int(time.time()), user_id, code_hash),
            )
            return "recovery" if used.rowcount == 1 else None

    # ---- refresh-токены: случайные, в БД только SHA-256-хеш, ротация ---- #
    @staticmethod
    def _rt_hash(raw: str) -> str:
        return hashlib.sha256(raw.encode()).hexdigest()

    def issue_refresh(self, user_id: str, family_id: str | None = None,
                      *, mfa_verified: bool = False) -> str:
        raw = secrets.token_urlsafe(32)
        family_id = family_id or uuid.uuid4().hex
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO refresh_tokens(
                       token_hash,user_id,family_id,expires_at,revoked,mfa_verified)
                   VALUES(?,?,?,?,0,?)""",
                (self._rt_hash(raw), user_id, family_id, int(time.time()) + _REFRESH_TTL,
                 int(mfa_verified)),
            )
        return raw

    def rotate_refresh(self, raw: str) -> tuple[str, str, bool] | None:
        """Атомарная ротация с reuse detection и сохранением MFA assurance.

        Возвращает ``(user_id, new_raw, mfa_verified)``. Повтор старого токена
        отзывает всё семейство, включая новый токен, выданный при первом обмене.
        """
        token_hash = self._rt_hash(raw)
        now = int(time.time())
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM refresh_tokens WHERE token_hash=?", (token_hash,)
            ).fetchone()
            if not row or row["expires_at"] < now:
                return None
            family_id = row["family_id"] or uuid.uuid4().hex
            if row["revoked"]:
                if row["family_id"]:
                    c.execute("UPDATE refresh_tokens SET revoked=1 WHERE family_id=?",
                              (family_id,))
                else:
                    # Legacy token без family metadata: fail-secure для пользователя.
                    c.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?",
                              (row["user_id"],))
                audit.warning("refresh REUSE id=%s family=%s", row["user_id"], family_id)
                return None

            new_raw = secrets.token_urlsafe(32)
            updated = c.execute(
                "UPDATE refresh_tokens SET revoked=1,used_at=?,family_id=? "
                "WHERE token_hash=? AND revoked=0",
                (now, family_id, token_hash),
            )
            if updated.rowcount != 1:
                c.execute("UPDATE refresh_tokens SET revoked=1 WHERE family_id=?",
                          (family_id,))
                audit.warning("refresh RACE/REUSE id=%s family=%s",
                              row["user_id"], family_id)
                return None
            c.execute(
                """INSERT INTO refresh_tokens(
                       token_hash,user_id,family_id,expires_at,revoked,mfa_verified)
                   VALUES(?,?,?,?,0,?)""",
                (self._rt_hash(new_raw), row["user_id"], family_id,
                 now + _REFRESH_TTL, int(row["mfa_verified"] or 0)),
            )
            return row["user_id"], new_raw, bool(row["mfa_verified"])

    def revoke_refresh(self, raw: str) -> None:
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE refresh_tokens SET revoked=1 WHERE token_hash=?",
                (self._rt_hash(raw),),
            )

    def revoke_all_refresh(self, user_id: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (user_id,))

    def create(self, email: str, pw_hash: str, role: str,
               brand_name: str | None = None, address: str | None = None,
               district: str | None = None, *, accepted_terms: bool = False,
               email_verified: bool = True, user_id: str | None = None) -> str:
        uid = user_id or uuid.uuid4().hex
        partner_id = uid if role == "partner" else None
        partner_status = "pending" if role == "partner" else None
        accepted_at = datetime.now(timezone.utc).isoformat() if accepted_terms else None
        with self._lock, self._conn() as c:
            c.execute(
                """INSERT INTO users(
                       id,email,email_verified,pw_hash,role,brand_name,address,district,partner_id,
                       partner_status,is_active,created_at,terms_accepted_at,terms_version)
                   VALUES(?,?,?,?,?,?,?,?,?,?,1,?,?,?)""",
                (uid, email.lower(), int(email_verified), pw_hash, role, brand_name, address,
                 district, partner_id, partner_status, datetime.now(timezone.utc).isoformat(), accepted_at,
                 _TERMS_VERSION if accepted_terms else None),
            )
        return uid

    def set_role(self, user_id: str, role: str) -> None:
        """Операторская операция для bootstrap/admin CLI; отзывает старые JWT."""
        if role not in {"customer", "partner", "admin"}:
            raise ValueError("неизвестная роль")
        with self._lock, self._conn() as c:
            cur = c.execute(
                "UPDATE users SET role=?, token_ver=COALESCE(token_ver,0)+1 WHERE id=?",
                (role, user_id),
            )
            if cur.rowcount != 1:
                raise ValueError("пользователь не найден")
        self.revoke_all_refresh(user_id)

    def partner_accounts(self, status: str | None = None) -> list[sqlite3.Row]:
        with self._lock, self._conn() as c:
            if status:
                return c.execute(
                    "SELECT * FROM users WHERE role='partner' AND partner_status=? "
                    "ORDER BY created_at", (status,),
                ).fetchall()
            return c.execute(
                "SELECT * FROM users WHERE role='partner' ORDER BY created_at"
            ).fetchall()

    def set_partner_status(self, user_id: str, status: str) -> sqlite3.Row:
        if status not in {"pending", "approved", "suspended", "rejected"}:
            raise ValueError("неизвестный partner status")
        with self._lock, self._conn() as c:
            row = c.execute(
                "SELECT * FROM users WHERE id=? AND role='partner'", (user_id,)
            ).fetchone()
            if not row:
                raise ValueError("partner account не найден")
            revoke = status != "approved"
            c.execute(
                "UPDATE users SET partner_status=?, "
                "token_ver=COALESCE(token_ver,0)+? WHERE id=?",
                (status, int(revoke), user_id),
            )
            updated = c.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        if revoke:
            self.revoke_all_refresh(user_id)
        return updated

    def issue_action_token(self, user_id: str, purpose: str, ttl: int) -> str:
        if purpose not in {"verify_email", "password_reset"}:
            raise ValueError("неизвестный token purpose")
        raw = secrets.token_urlsafe(32)
        now = int(time.time())
        with self._lock, self._conn() as c:
            c.execute(
                "UPDATE action_tokens SET used_at=? WHERE user_id=? AND purpose=? AND used_at IS NULL",
                (now, user_id, purpose),
            )
            c.execute(
                """INSERT INTO action_tokens(token_hash,user_id,purpose,expires_at,created_at)
                   VALUES(?,?,?,?,?)""",
                (self._rt_hash(raw), user_id, purpose, now + ttl, now),
            )
        return raw

    def verify_email_token(self, raw: str) -> str | None:
        now = int(time.time())
        with self._lock, self._conn() as c:
            row = c.execute(
                """SELECT * FROM action_tokens WHERE token_hash=? AND purpose='verify_email'
                   AND used_at IS NULL AND expires_at>=?""",
                (self._rt_hash(raw), now),
            ).fetchone()
            if not row:
                return None
            used = c.execute(
                "UPDATE action_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL",
                (now, row["token_hash"]),
            )
            if used.rowcount != 1:
                return None
            c.execute("UPDATE users SET email_verified=1 WHERE id=?", (row["user_id"],))
            return row["user_id"]

    def reset_password_token(self, raw: str, new_hash: str) -> str | None:
        now = int(time.time())
        with self._lock, self._conn() as c:
            row = c.execute(
                """SELECT * FROM action_tokens WHERE token_hash=? AND purpose='password_reset'
                   AND used_at IS NULL AND expires_at>=?""",
                (self._rt_hash(raw), now),
            ).fetchone()
            if not row:
                return None
            used = c.execute(
                "UPDATE action_tokens SET used_at=? WHERE token_hash=? AND used_at IS NULL",
                (now, row["token_hash"]),
            )
            if used.rowcount != 1:
                return None
            c.execute(
                "UPDATE users SET pw_hash=?,token_ver=COALESCE(token_ver,0)+1 WHERE id=?",
                (new_hash, row["user_id"]),
            )
            c.execute("UPDATE refresh_tokens SET revoked=1 WHERE user_id=?", (row["user_id"],))
            return row["user_id"]

    def mark_email_verified(self, user_id: str) -> None:
        with self._lock, self._conn() as c:
            cur = c.execute("UPDATE users SET email_verified=1 WHERE id=?", (user_id,))
            if cur.rowcount != 1:
                raise ValueError("пользователь не найден")

    def update_password_hash(self, user_id: str, pw_hash: str) -> None:
        """Rehash после успешной проверки; credential/session semantics не меняются."""
        with self._lock, self._conn() as c:
            c.execute("UPDATE users SET pw_hash=? WHERE id=?", (pw_hash, user_id))


accounts = Accounts()


# --------------------------------------------------------------------------- #
#  Схемы (пароль-хеш НИКОГДА не попадает в ответ)
# --------------------------------------------------------------------------- #
class RegisterInput(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=128)
    role: Literal["customer", "partner"] = "customer"
    brand_name: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    district: str | None = Field(default=None, max_length=80)
    accepted_terms: Literal[True]

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
    email: str = Field(..., max_length=254)
    password: str = Field(..., max_length=128)
    mfa_code: str | None = Field(default=None, max_length=20)


class PublicUser(BaseModel):
    id: str
    email: str
    email_verified: bool
    role: str
    brand_name: str | None = None
    address: str | None = None
    district: str | None = None
    partner_id: str | None = None
    partner_status: str | None = None
    auth_methods: list[str] = Field(default_factory=list, exclude=True)
    mfa_enabled: bool = Field(default=False, exclude=True)


class AuthResult(BaseModel):
    """Bearer API result. Browser frontend uses SessionResult + HttpOnly cookies."""

    access_token: str
    refresh_token: str = ""
    token_type: str = "bearer"
    user: PublicUser


class SessionResult(BaseModel):
    user: PublicUser
    csrf_token: str
    auth_mode: Literal["cookie"] = "cookie"


def _set_session_cookies(response: Response, result: AuthResult) -> str:
    csrf_token = secrets.token_urlsafe(32)
    common = {"secure": _PRODUCTION, "samesite": "strict"}
    response.set_cookie(
        _ACCESS_COOKIE, result.access_token, max_age=_TOKEN_TTL, httponly=True,
        path="/", **common,
    )
    response.set_cookie(
        _REFRESH_COOKIE, result.refresh_token, max_age=_REFRESH_TTL, httponly=True,
        path="/session", **common,
    )
    response.set_cookie(
        _CSRF_COOKIE, csrf_token, max_age=_REFRESH_TTL, httponly=False,
        path="/", **common,
    )
    response.headers["Cache-Control"] = "no-store"
    return csrf_token


def _clear_session_cookies(response: Response) -> None:
    response.delete_cookie(_ACCESS_COOKIE, path="/", secure=_PRODUCTION, samesite="strict")
    response.delete_cookie(
        _REFRESH_COOKIE, path="/session", secure=_PRODUCTION, samesite="strict"
    )
    response.delete_cookie(_CSRF_COOKIE, path="/", secure=_PRODUCTION, samesite="strict")
    response.headers["Clear-Site-Data"] = '"cache", "cookies"'
    response.headers["Cache-Control"] = "no-store"


def _public(row: sqlite3.Row, auth_methods: list[str] | None = None) -> PublicUser:
    return PublicUser(
        id=row["id"], email=row["email"], email_verified=bool(row["email_verified"]),
        role=row["role"],
        brand_name=row["brand_name"], address=row["address"], district=row["district"],
        partner_id=row["partner_id"], partner_status=row["partner_status"],
        auth_methods=auth_methods or [], mfa_enabled=bool(row["mfa_enabled"]),
    )


# --------------------------------------------------------------------------- #
#  Эндпоинты
# --------------------------------------------------------------------------- #
def _ip(req: HttpRequest) -> str:
    return req.client.host if req and req.client else "?"


def _email_tag(email: str) -> str:
    """Стабильная корреляция auth events без plaintext email в логах."""
    return hashlib.sha256(email.strip().lower().encode()).hexdigest()[:16]


@router.post("/auth/register", response_model=AuthResult, status_code=201,
             dependencies=[Depends(auth_rate_limit)])
def register(data: RegisterInput, request: HttpRequest) -> AuthResult:
    if accounts.by_email(data.email):
        audit.info("register DENIED email_tag=%s ip=%s", _email_tag(data.email), _ip(request))
        raise HTTPException(409, "Email уже зарегистрирован")
    brand = data.brand_name.strip() if data.role == "partner" and data.brand_name else None
    addr = data.address.strip() if data.role == "partner" and data.address else None
    district = data.district.strip() if data.role == "partner" and data.district else None
    if data.role == "partner" and not brand:
        raise HTTPException(422, "Для заведения укажите название")
    if data.role == "partner" and not addr:
        raise HTTPException(422, "Для заведения укажите адрес")
    role = data.role  # admin создаётся только оператором через tools/create_admin.py
    uid = accounts.create(
        data.email, hash_password(data.password), role, brand, addr, district,
        accepted_terms=data.accepted_terms, email_verified=False,
    )
    row = accounts.by_id(uid)
    from .email_delivery import send_verification
    verification = accounts.issue_action_token(uid, "verify_email", 24 * 3600)
    delivered = send_verification(row["email"], verification)
    audit.info("email-verification issued id=%s delivered=%s", uid, delivered)
    audit.info("register OK id=%s role=%s email_tag=%s ip=%s",
               uid, role, _email_tag(data.email), _ip(request))
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
        audit.warning("login FAIL email_tag=%s ip=%s", _email_tag(email), _ip(request))
        raise HTTPException(401, "Неверный email или пароль")
    if not row["is_active"]:
        raise HTTPException(403, "Аккаунт отключён")
    if row["role"] == "partner" and row["partner_status"] in {"suspended", "rejected"}:
        raise HTTPException(403, f"Доступ заведения ограничен: {row['partner_status']}")
    if password_needs_rehash(row["pw_hash"]):
        accounts.update_password_hash(row["id"], hash_password(data.password))
        row = accounts.by_id(row["id"])
        audit.info("password-rehash id=%s algorithm=argon2id", row["id"])
    mfa_verified = False
    factor = None
    if row["role"] == "admin":
        if not row["mfa_enabled"]:
            audit.error("admin-login BLOCKED mfa-not-configured id=%s", row["id"])
            raise HTTPException(403, "Для admin не настроена MFA; запустите create_admin.py")
        factor = accounts.consume_mfa(row["id"], data.mfa_code or "")
        if not factor:
            _jail_fail(email)
            audit.warning("admin-login MFA-FAIL id=%s ip=%s", row["id"], _ip(request))
            raise HTTPException(401, "Неверный MFA или recovery-код")
        mfa_verified = True
    _jail_reset(email)
    amr = ["pwd", factor or "pwd"] if mfa_verified else ["pwd"]
    audit.info("login OK id=%s mfa=%s ip=%s", row["id"], mfa_verified, _ip(request))
    return AuthResult(
        access_token=create_token(
            row["id"], row["role"], ver=_row_token_ver(row), mfa_verified=mfa_verified
        ),
        refresh_token=accounts.issue_refresh(row["id"], mfa_verified=mfa_verified),
        user=_public(row, amr),
    )


class RefreshInput(BaseModel):
    refresh_token: str = Field(..., min_length=32, max_length=256)


@router.post("/auth/refresh", response_model=AuthResult, dependencies=[Depends(auth_rate_limit)])
def refresh(data: RefreshInput, request: HttpRequest) -> AuthResult:
    """Обновить короткий access-токен. Refresh ротируется: старый сгорает."""
    rotated = accounts.rotate_refresh(data.refresh_token)
    uid, new_refresh, mfa_verified = rotated if rotated else (None, None, False)
    row = accounts.by_id(uid) if uid else None
    if not row or not row["is_active"]:
        audit.warning("refresh FAIL ip=%s", _ip(request))
        raise HTTPException(401, "Refresh-токен недействителен, войдите заново")
    if row["role"] == "admin" and not mfa_verified:
        accounts.revoke_all_refresh(row["id"])
        raise HTTPException(401, "Admin refresh не подтверждён MFA")
    amr = ["pwd", "mfa"] if mfa_verified else ["pwd"]
    return AuthResult(
        access_token=create_token(
            row["id"], row["role"], ver=_row_token_ver(row), mfa_verified=mfa_verified
        ),
        refresh_token=new_refresh, user=_public(row, amr),
    )


# /auth/logout-all — ниже, после определения current_user


def _row_token_ver(row) -> int:
    try:
        return int(row["token_ver"] or 0)
    except (KeyError, IndexError, TypeError):
        return 0


def _presented_access_token(request: HttpRequest, authorization: str | None) -> str | None:
    """Bearer имеет приоритет; cookie используется браузерным same-origin BFF."""
    if authorization:
        if not authorization.lower().startswith("bearer "):
            return None
        return authorization.split(" ", 1)[1]
    return request.cookies.get(_ACCESS_COOKIE)


def optional_user(
    request: HttpRequest,
    authorization: str | None = Header(default=None),
) -> PublicUser | None:
    """Мягкая авторизация: Bearer/cookie валиден → юзер, иначе гость."""
    token = _presented_access_token(request, authorization)
    if not token:
        # CSRF marker живёт дольше access cookie: браузерная сессия истекла,
        # поэтому frontend должен refresh'нуть её, а не незаметно стать гостем.
        if request.cookies.get(_CSRF_COOKIE):
            raise HTTPException(401, "Сессия истекла")
        return None
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(401, f"Токен: {exc}") from exc
    row = accounts.by_id(payload["sub"])
    if (not row or not row["is_active"]
            or payload.get("ver", 0) != _row_token_ver(row)):
        raise HTTPException(401, "Сессия недействительна")
    return _public(row, payload.get("amr", []))


def current_user(
    request: HttpRequest,
    authorization: str | None = Header(default=None),
) -> PublicUser:
    token = _presented_access_token(request, authorization)
    if not token:
        raise HTTPException(401, "Нужна активная сессия или Bearer-токен")
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(401, f"Токен: {exc}") from exc
    row = accounts.by_id(payload["sub"])
    if not row or not row["is_active"]:
        raise HTTPException(401, "Пользователь не найден или отключён")
    if payload.get("ver", 0) != _row_token_ver(row):
        # пароль менялся после выпуска токена — все старые сессии отозваны
        raise HTTPException(401, "Сессия недействительна, войдите заново")
    return _public(row, payload.get("amr", []))


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
    old_password: str = Field(..., max_length=128)
    new_password: str = Field(..., max_length=128)

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
    mfa_verified = "mfa" in user.auth_methods
    return {"status": "ok",
            "access_token": create_token(
                user.id, row["role"], ver=_row_token_ver(row), mfa_verified=mfa_verified
            ),
            "refresh_token": accounts.issue_refresh(user.id, mfa_verified=mfa_verified)}


# --------------------------------------------------------------------------- #
#  Email verification / password recovery (single-use hashed tokens).
# --------------------------------------------------------------------------- #
class ActionTokenInput(BaseModel):
    token: str = Field(..., min_length=32, max_length=256)


class ForgotPasswordInput(BaseModel):
    email: str = Field(..., max_length=254)


class ResetPasswordInput(ActionTokenInput):
    new_password: str = Field(..., max_length=128)

    @field_validator("new_password")
    @classmethod
    def _strong(cls, value: str) -> str:
        return RegisterInput._password_strong(value)


@router.post("/auth/email/verify/request", status_code=202,
             dependencies=[Depends(auth_rate_limit)])
def request_email_verification(
    request: HttpRequest,
    user: PublicUser = Depends(current_user),
) -> dict:
    if user.email_verified:
        return {"status": "already_verified"}
    from .email_delivery import send_verification
    raw = accounts.issue_action_token(user.id, "verify_email", 24 * 3600)
    delivered = send_verification(user.email, raw)
    audit.info("email-verification reissued id=%s delivered=%s ip=%s",
               user.id, delivered, _ip(request))
    return {"status": "accepted"}


@router.post("/auth/email/verify/confirm", dependencies=[Depends(auth_rate_limit)])
def confirm_email_verification(data: ActionTokenInput, request: HttpRequest) -> dict:
    uid = accounts.verify_email_token(data.token)
    if not uid:
        raise HTTPException(400, "Verification token недействителен или истёк")
    audit.info("email VERIFIED id=%s ip=%s", uid, _ip(request))
    return {"status": "verified"}


@router.post("/auth/password/forgot", status_code=202,
             dependencies=[Depends(auth_rate_limit)])
def forgot_password(data: ForgotPasswordInput, request: HttpRequest) -> dict:
    from .email_delivery import send_password_reset
    email = data.email.strip().lower()
    row = accounts.by_email(email)
    if row and row["is_active"]:
        raw = accounts.issue_action_token(row["id"], "password_reset", 30 * 60)
        delivered = send_password_reset(row["email"], raw)
        audit.info("password-reset issued id=%s delivered=%s ip=%s",
                   row["id"], delivered, _ip(request))
    else:
        audit.info("password-reset accepted unknown_email_tag=%s ip=%s",
                   _email_tag(email), _ip(request))
    # Одинаковый ответ: endpoint не раскрывает существование аккаунта.
    return {"status": "accepted"}


@router.post("/auth/password/reset", dependencies=[Depends(auth_rate_limit)])
def reset_password(data: ResetPasswordInput, request: HttpRequest) -> dict:
    uid = accounts.reset_password_token(data.token, hash_password(data.new_password))
    if not uid:
        raise HTTPException(400, "Reset token недействителен или истёк")
    audit.warning("password-reset COMPLETE id=%s ip=%s sessions=revoked", uid, _ip(request))
    return {"status": "reset", "sessions_revoked": True}


# --------------------------------------------------------------------------- #
#  Same-origin browser session (BFF): JS никогда не получает access/refresh.
# --------------------------------------------------------------------------- #
@router.post("/session/register", response_model=SessionResult, status_code=201,
             tags=["Session"], dependencies=[Depends(auth_rate_limit)])
def session_register(data: RegisterInput, request: HttpRequest,
                     response: Response) -> SessionResult:
    result = register(data, request)
    csrf = _set_session_cookies(response, result)
    return SessionResult(user=result.user, csrf_token=csrf)


@router.post("/session/login", response_model=SessionResult, tags=["Session"],
             dependencies=[Depends(auth_rate_limit)])
def session_login(data: LoginInput, request: HttpRequest,
                  response: Response) -> SessionResult:
    result = login(data, request)
    csrf = _set_session_cookies(response, result)
    return SessionResult(user=result.user, csrf_token=csrf)


@router.post("/session/refresh", response_model=SessionResult, tags=["Session"],
             dependencies=[Depends(auth_rate_limit)])
def session_refresh(request: HttpRequest, response: Response) -> SessionResult:
    raw = request.cookies.get(_REFRESH_COOKIE)
    if not raw:
        raise HTTPException(401, "Refresh-cookie отсутствует")
    result = refresh(RefreshInput(refresh_token=raw), request)
    csrf = _set_session_cookies(response, result)
    return SessionResult(user=result.user, csrf_token=csrf)


@router.get("/session/me", response_model=PublicUser, tags=["Session"])
def session_me(user: PublicUser = Depends(current_user)) -> PublicUser:
    return user


@router.post("/session/change-password", response_model=SessionResult, tags=["Session"],
             dependencies=[Depends(auth_rate_limit)])
def session_change_password(
    data: ChangePasswordInput,
    request: HttpRequest,
    response: Response,
    user: PublicUser = Depends(current_user),
) -> SessionResult:
    result = change_password(data, request, user)
    auth = AuthResult(
        access_token=result["access_token"], refresh_token=result["refresh_token"], user=user
    )
    csrf = _set_session_cookies(response, auth)
    return SessionResult(user=user, csrf_token=csrf)


@router.post("/session/logout", tags=["Session"])
def session_logout(request: HttpRequest, response: Response) -> dict:
    raw = request.cookies.get(_REFRESH_COOKIE)
    if raw:
        accounts.revoke_refresh(raw)
    _clear_session_cookies(response)
    audit.info("logout current-device ip=%s", _ip(request))
    return {"status": "ok"}


@router.post("/session/logout-all", tags=["Session"])
def session_logout_all(
    request: HttpRequest,
    response: Response,
    user: PublicUser = Depends(current_user),
) -> dict:
    result = logout_all(request, user)
    _clear_session_cookies(response)
    return result


# --------------------------------------------------------------------------- #
#  Ролевой доступ: deny-by-default. Статическая Pages-демка использует свой
#  browser store; серверные mutation/private endpoints никогда не открываются
#  из-за забытой переменной окружения.
# --------------------------------------------------------------------------- #
def require_role(*roles: str):
    """Dependency-фабрика: всегда требует валидную Bearer/cookie сессию и роль."""
    def _dep(
        request: HttpRequest,
        authorization: str | None = Header(default=None),
    ) -> PublicUser:
        user = current_user(request, authorization)
        if roles and user.role not in roles:
            raise HTTPException(403, "Недостаточно прав")
        if user.role == "admin" and (not user.mfa_enabled or "mfa" not in user.auth_methods):
            audit.warning("admin-access DENIED no-mfa id=%s", user.id)
            raise HTTPException(403, "Для admin требуется MFA-подтверждённая сессия")
        return user
    return _dep
