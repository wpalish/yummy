"""Вход через Telegram Login Widget — серверная проверка подписи (HMAC-SHA256).

Активация (действия владельца):
1. @BotFather → создать бота → токен положить в env TELEGRAM_BOT_TOKEN.
2. BotFather → Bot Settings → Domain → указать домен сайта.
3. На фронте подключить виджет telegram-widget.js с именем бота.

Пока токен не задан, эндпоинт отвечает 501 — инфраструктура готова, но выключена.
Данные фронтенда НЕ считаются доверенными: подпись перепроверяется на сервере.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import time

from fastapi import APIRouter, HTTPException

router = APIRouter()

_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
MAX_AGE_SECONDS = 86400  # сутки: защита от replay-атак устаревшими данными


def verify_telegram_auth(data: dict, token: str, max_age: int = MAX_AGE_SECONDS) -> dict:
    """Проверить, что данные действительно подписаны Telegram.

    Алгоритм из документации Telegram Login Widget:
    secret = SHA256(bot_token); hash = HMAC_SHA256(secret, "k=v\\n..." по алфавиту).
    Бросает ValueError, если подпись не сходится или данные устарели.
    """
    payload = {k: v for k, v in data.items() if v is not None}
    their_hash = payload.pop("hash", None)
    if not their_hash:
        raise ValueError("отсутствует hash")

    check_string = "\n".join(f"{k}={v}" for k, v in sorted(payload.items()))
    secret = hashlib.sha256(token.encode()).digest()
    expected = hmac.new(secret, check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, their_hash):
        raise ValueError("подпись не от Telegram")
    if time.time() - int(payload.get("auth_date", 0)) > max_age:
        raise ValueError("данные авторизации устарели")
    return payload


@router.get("/auth/telegram", tags=["Auth"])
async def telegram_auth(
    id: int,
    first_name: str,
    auth_date: int,
    hash: str,
    last_name: str | None = None,
    username: str | None = None,
    photo_url: str | None = None,
) -> dict:
    """Callback Telegram Login Widget: проверяем подпись и возвращаем профиль."""
    if not _TOKEN:
        raise HTTPException(501, "Telegram-вход не настроен: задайте TELEGRAM_BOT_TOKEN")

    data = {
        "id": str(id), "first_name": first_name, "auth_date": str(auth_date),
        "hash": hash, "last_name": last_name, "username": username,
        "photo_url": photo_url,
    }
    try:
        user = verify_telegram_auth(data, _TOKEN)
    except ValueError as exc:
        raise HTTPException(401, f"Telegram auth: {exc}") from exc
    return {"status": "ok", "user": user}
