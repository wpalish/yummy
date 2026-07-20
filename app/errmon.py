"""Мониторинг необработанных ошибок: прод больше не 500-ит молча.

Два канала, оба опциональны (нет конфигурации → no-op, как ai.py/notify.py):
  - Sentry: SENTRY_DSN в env → событие через store-endpoint API (голый httpx,
    без sentry-sdk — в духе stdlib-подхода проекта);
  - Telegram: YUMMY_ORDERS_CHAT_ID (тот же опс-чат, что и брони) → короткое
    сообщение об ошибке.

Анти-спам: одна и та же ошибка (тип+эндпоинт) шлётся не чаще раза в 10 минут —
падающий в цикле эндпоинт не устраивает бомбардировку чата.
"""
from __future__ import annotations

import logging
import os
import time
import traceback
from urllib.parse import urlparse

import httpx

log = logging.getLogger("yummy.errmon")

_TIMEOUT = 4.0
_DEDUP_WINDOW = 600.0
_last_sent: dict[str, float] = {}


def _dedup(key: str) -> bool:
    """True — можно слать; False — эта ошибка уже уходила недавно."""
    now = time.monotonic()
    if now - _last_sent.get(key, 0.0) < _DEDUP_WINDOW:
        return False
    if len(_last_sent) > 512:                    # не растим карту бесконечно
        _last_sent.clear()
    _last_sent[key] = now
    return True


def _sentry_send(exc: BaseException, path: str) -> bool:
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    try:
        u = urlparse(dsn)
        project = u.path.strip("/")
        endpoint = f"{u.scheme}://{u.hostname}/api/{project}/store/"
        headers = {"X-Sentry-Auth": (
            f"Sentry sentry_version=7, sentry_key={u.username}, sentry_client=yummy/1.0")}
        event = {
            "level": "error",
            "platform": "python",
            "transaction": path,
            "exception": {"values": [{
                "type": type(exc).__name__, "value": str(exc)[:500],
                "stacktrace": {"frames": [
                    {"filename": f.filename, "function": f.name, "lineno": f.lineno}
                    for f in traceback.extract_tb(exc.__traceback__)[-20:]]},
            }]},
        }
        httpx.post(endpoint, json=event, headers=headers, timeout=_TIMEOUT)
        return True
    except Exception as e:                       # noqa: BLE001 — монитор не роняет
        log.warning("sentry send failed: %s", e)
        return False


def _telegram_send(exc: BaseException, path: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("YUMMY_ORDERS_CHAT_ID", "").strip()
    if not (token and chat):
        return False
    try:
        httpx.post(f"https://api.telegram.org/bot{token}/sendMessage",
                   json={"chat_id": chat,
                         "text": f"🔥 500 на {path}\n{type(exc).__name__}: {str(exc)[:300]}"},
                   timeout=_TIMEOUT)
        return True
    except Exception as e:                       # noqa: BLE001
        log.warning("telegram alert failed: %s", e)
        return False


def report(exc: BaseException, path: str = "?") -> None:
    """Сообщить о необработанной ошибке во все настроенные каналы."""
    if not _dedup(f"{type(exc).__name__}:{path}"):
        return
    sent_sentry = _sentry_send(exc, path)
    sent_tg = _telegram_send(exc, path)
    if not (sent_sentry or sent_tg):
        log.debug("errmon: каналы не настроены (SENTRY_DSN / YUMMY_ORDERS_CHAT_ID)")
