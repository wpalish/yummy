"""Отправка писем через SMTP — stdlib smtplib, без зависимостей.

Настройка (env): YUMMY_SMTP_HOST, YUMMY_SMTP_PORT (587 STARTTLS / 465 SSL),
YUMMY_SMTP_USER, YUMMY_SMTP_PASS, YUMMY_SMTP_FROM. Подходит любой провайдер
(Gmail app-password, Brevo, Resend SMTP…).

Graceful degradation — как ai.py/notify.py: без настройки фича не 500-ит,
а честно отвечает «письма не настроены» (важно: сам факт настроенности не
раскрывает существование адресата).
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("yummy.mail")


def is_configured() -> bool:
    return bool(os.getenv("YUMMY_SMTP_HOST") and os.getenv("YUMMY_SMTP_FROM"))


def send(to: str, subject: str, body: str) -> bool:
    """True — письмо ушло. Ошибки логируем и возвращаем False (не 500)."""
    if not is_configured():
        return False
    host = os.getenv("YUMMY_SMTP_HOST", "").strip()
    port = int(os.getenv("YUMMY_SMTP_PORT", "587").strip() or "587")
    user = os.getenv("YUMMY_SMTP_USER", "").strip()
    # Gmail показывает app-пароль с пробелами («abcd efgh ijkl mnop») для
    # читаемости, но SMTP-логин требует его БЕЗ пробелов — снимаем их.
    password = os.getenv("YUMMY_SMTP_PASS", "").replace(" ", "").strip()
    msg = EmailMessage()
    msg["From"] = os.getenv("YUMMY_SMTP_FROM", "")
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
