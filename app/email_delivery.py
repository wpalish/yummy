"""Transactional email adapter: fixed Resend endpoint or bounded dev outbox.

Raw verification/reset tokens никогда не логируются и не сохраняются в SQLite.
"""
from __future__ import annotations

import hashlib
import logging
import os
import threading
from collections import deque

import httpx

log = logging.getLogger("yummy.email")
_MODE = os.getenv("YUMMY_EMAIL_MODE", "development").lower()
_PRODUCTION = os.getenv("YUMMY_ENV", "").lower() == "production"
_API_KEY = os.getenv("RESEND_API_KEY", "")
_FROM = os.getenv("YUMMY_EMAIL_FROM", "")
_PUBLIC_URL = os.getenv("YUMMY_PUBLIC_URL", "http://localhost:8021").rstrip("/")
_RESEND_URL = "https://api.resend.com/emails"
_DEV_OUTBOX: deque[dict] = deque(maxlen=100)
_LOCK = threading.Lock()


def assert_email_config() -> None:
    if _MODE not in {"development", "disabled", "resend"}:
        raise RuntimeError("YUMMY_EMAIL_MODE: development, disabled или resend")
    if _PRODUCTION and _MODE == "development":
        raise RuntimeError("production запрещает development email outbox")
    if _MODE == "resend" and (not _API_KEY or not _FROM or not _PUBLIC_URL.startswith("https://")):
        raise RuntimeError("resend требует RESEND_API_KEY, YUMMY_EMAIL_FROM и HTTPS YUMMY_PUBLIC_URL")


def _tag(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()[:16]


def _deliver(to: str, subject: str, text: str) -> bool:
    if _MODE == "disabled":
        log.warning("email disabled recipient_tag=%s", _tag(to))
        return False
    if _MODE == "development" and not _PRODUCTION:
        with _LOCK:
            _DEV_OUTBOX.append({"to": to, "subject": subject, "text": text})
        log.info("email queued dev recipient_tag=%s", _tag(to))
        return True
    try:
        response = httpx.post(
            _RESEND_URL,
            headers={"Authorization": f"Bearer {_API_KEY}", "Content-Type": "application/json"},
            json={"from": _FROM, "to": [to], "subject": subject, "text": text},
            timeout=10.0,
        )
        response.raise_for_status()
    except httpx.HTTPError:
        log.exception("email delivery failed recipient_tag=%s", _tag(to))
        return False
    log.info("email delivered recipient_tag=%s", _tag(to))
    return True


def send_verification(to: str, token: str) -> bool:
    url = f"{_PUBLIC_URL}/?verify={token}"
    return _deliver(to, "Подтвердите email в Yummy", f"Откройте ссылку в течение 24 часов:\n{url}")


def send_password_reset(to: str, token: str) -> bool:
    url = f"{_PUBLIC_URL}/?reset={token}"
    return _deliver(to, "Сброс пароля Yummy", f"Откройте ссылку в течение 30 минут:\n{url}\nЕсли это не вы — ничего не делайте.")
