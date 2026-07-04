"""Аутентификация привилегированных эндпоинтов (партнёр/админ).

MVP использует общие токены-секреты, задаваемые через переменные окружения
``ADMIN_TOKEN`` и ``PARTNER_TOKEN``. Токен передаётся в заголовке запроса
(``X-Admin-Token`` / ``X-Partner-Token``).

Поведение «fail closed»: если переменная окружения не задана, соответствующие
эндпоинты недоступны (503). Так витрина магазина остаётся публичной, а данные
клиентов (имя, телефон), возвраты и выдача не открыты анонимно.
"""
from __future__ import annotations

import os
import secrets

from fastapi import Header, HTTPException


def _require(provided: str | None, env_name: str, role: str) -> None:
    expected = os.environ.get(env_name)
    if not expected:
        raise HTTPException(
            503,
            f"{role}: доступ не настроен на сервере (переменная {env_name} не задана)",
        )
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(401, f"{role}: неверный или отсутствующий токен")


def require_admin(x_admin_token: str | None = Header(default=None)) -> None:
    _require(x_admin_token, "ADMIN_TOKEN", "Админ")


def require_partner(x_partner_token: str | None = Header(default=None)) -> None:
    _require(x_partner_token, "PARTNER_TOKEN", "Партнёр")
