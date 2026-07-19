"""TOTP (RFC 6238) на stdlib — hmac + struct, без pyotp.

Тот же алгоритм, что в Google Authenticator / 1Password: HMAC-SHA1 по счётчику
30-секундных интервалов, динамическое усечение до 6 цифр. Секрет — base32
(так его понимают все аутентификаторы).
"""
from __future__ import annotations

import base64
import hmac
import secrets
import struct
import time
import urllib.parse


def new_secret() -> str:
    """160-битный секрет в base32 (стандарт для отп-приложений)."""
    return base64.b32encode(secrets.token_bytes(20)).decode()


def code_at(secret_b32: str, t: float | None = None, step: int = 30) -> str:
    key = base64.b32decode(secret_b32, casefold=True)
    counter = int((t if t is not None else time.time()) // step)
    msg = struct.pack(">Q", counter)
    digest = hmac.new(key, msg, "sha1").digest()
    offset = digest[-1] & 0x0F
    num = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{num % 1_000_000:06d}"


def verify(secret_b32: str, code: str, window: int = 1) -> bool:
    """Код валиден в текущем окне ±window шагов (дрейф часов телефона)."""
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    now = time.time()
    return any(hmac.compare_digest(code_at(secret_b32, now + i * 30), code)
               for i in range(-window, window + 1))


def otpauth_url(secret_b32: str, account: str, issuer: str = "Yummy") -> str:
    """otpauth://-ссылка для QR (её сканирует приложение-аутентификатор)."""
    label = urllib.parse.quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}"
            f"&issuer={urllib.parse.quote(issuer)}&algorithm=SHA1&digits=6&period=30")
