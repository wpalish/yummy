"""Отправка писем — два транспорта, оба на уже имеющихся зависимостях.

1. **HTTP API (Resend)** — приоритетный. Настройка: YUMMY_RESEND_KEY + YUMMY_SMTP_FROM.
   Работает по HTTPS/443 — важно для хостингов, которые режут исходящий SMTP
   (Render free блокирует порты 25/465/587 → OSError «Network is unreachable»).
2. **SMTP (stdlib smtplib)** — фолбэк для локали/своего хоста. Настройка:
   YUMMY_SMTP_HOST, YUMMY_SMTP_PORT (587 STARTTLS / 465 SSL), YUMMY_SMTP_USER,
   YUMMY_SMTP_PASS, YUMMY_SMTP_FROM.

Graceful degradation — как ai.py/notify.py: без настройки фича не 500-ит, а честно
отвечает «письма не настроены» (сам факт настроенности не раскрывает существование
адресата).
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

import httpx

log = logging.getLogger("yummy.mail")

_RESEND_ENDPOINT = "https://api.resend.com/emails"


def _from() -> str:
    return os.getenv("YUMMY_SMTP_FROM", "").strip()


def _resend_configured() -> bool:
    return bool(os.getenv("YUMMY_RESEND_KEY", "").strip() and _from())


def _smtp_configured() -> bool:
    return bool(os.getenv("YUMMY_SMTP_HOST", "").strip() and _from())


def is_configured() -> bool:
    return _resend_configured() or _smtp_configured()


def send(to: str, subject: str, body: str) -> bool:
    """True — письмо ушло. Ошибки логируем и возвращаем False (не 500).

    Resend (HTTP) в приоритете, т.к. работает там, где хостинг режет SMTP.
    """
    if _resend_configured():
        if _send_resend(to, subject, body):
            return True
        # если Resend упал, а SMTP тоже настроен — пробуем его
    if _smtp_configured():
        return _send_smtp(to, subject, body)
    return False


def _send_resend(to: str, subject: str, body: str) -> bool:
    key = os.getenv("YUMMY_RESEND_KEY", "").strip()
    payload = {"from": _from(), "to": [to], "subject": subject, "text": body}
    try:
        resp = httpx.post(
            _RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=15.0,
        )
        if resp.status_code < 300:
            return True
        # тело ответа Resend содержит причину (домен не верифицирован и т.п.);
        # секрет (ключ) не логируем
        log.warning("resend send failed status=%s body=%s", resp.status_code, resp.text[:300])
        return False
    except httpx.HTTPError as exc:
        log.warning("resend send error: %s: %s", type(exc).__name__, exc)
        return False


def _send_smtp(to: str, subject: str, body: str) -> bool:
    host = os.getenv("YUMMY_SMTP_HOST", "").strip()
    port = int(os.getenv("YUMMY_SMTP_PORT", "587").strip() or "587")
    user = os.getenv("YUMMY_SMTP_USER", "").strip()
    # Gmail показывает app-пароль с пробелами («abcd efgh ijkl mnop») для
    # читаемости, но SMTP-логин требует его БЕЗ пробелов — снимаем их.
    password = os.getenv("YUMMY_SMTP_PASS", "").replace(" ", "").strip()
    msg = EmailMessage()
    msg["From"] = _from()
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=15) as s:
                if user:
                    s.login(user, password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=15) as s:
                s.starttls()
                if user:
                    s.login(user, password)
                s.send_message(msg)
        return True
    except Exception as exc:                    # noqa: BLE001 — наружу не 500
        # тип ошибки помогает диагностике: auth (неверный app-пароль),
        # timeout (порт закрыт), connect (неверный host). Секрет не логируем.
        log.warning("smtp send failed host=%s port=%s user=%s: %s: %s",
                    host, port, user, type(exc).__name__, exc)
        return False
