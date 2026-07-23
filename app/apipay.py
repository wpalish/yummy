"""Kaspi-платежи через ApiPay.kz — REST-шлюз, httpx, без SDK.

Как ai.py/notify.py: graceful degradation. Нет APIPAY_API_KEY → is_configured()
False, создание инвойса поднимает PaymentUnavailable (роут отдаёт 503, не 500) —
поведение пилота (demo/disabled) не меняется. Контракт: https://apipay.kz/llms.txt

Деньги идут напрямую партнёру (его Kaspi через ApiPay-организацию); Yummy лишь
инициирует инвойс и слушает вебхук о статусе, комиссию ведёт своим ledger'ом.
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
import re

import httpx

log = logging.getLogger("yummy.apipay")

_BASE = "https://api.apipay.kz/api/v1"
_TIMEOUT = 10.0


class PaymentUnavailable(Exception):
    """Шлюз не настроен или временно недоступен — покупку не проводим."""


def _key() -> str:
    return os.getenv("APIPAY_API_KEY", "").strip()


def _webhook_secret() -> str:
    return os.getenv("APIPAY_WEBHOOK_SECRET", "").strip()


def is_configured() -> bool:
    return bool(_key())


def normalize_phone(raw: str) -> str | None:
    """К формату ApiPay: 8XXXXXXXXXX (11 цифр, ведущая 8, без +7/пробелов)."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) == 11 and digits[0] == "7":      # 7XXXXXXXXXX → 8XXXXXXXXXX
        digits = "8" + digits[1:]
    elif len(digits) == 10:                          # XXXXXXXXXX → 8XXXXXXXXXX
        digits = "8" + digits
    return digits if len(digits) == 11 and digits[0] == "8" else None


def _headers() -> dict[str, str]:
    return {"X-API-Key": _key(), "Content-Type": "application/json"}


def create_invoice(phone: str, amount: int, description: str,
                   idempotency_key: str) -> dict:
    """Создать инвойс на оплату. amount — тенге (целое). Возвращает тело ответа
    ApiPay (id, status: обычно 'processing'). Ошибки → PaymentUnavailable."""
    if not is_configured():
        raise PaymentUnavailable("APIPAY_API_KEY не задан")
    ph = normalize_phone(phone)
    if not ph:
        raise PaymentUnavailable("Некорректный номер телефона для Kaspi")
    body = {
        "phone_number": ph,
        "amount": float(amount),
        "description": (description or "")[:500],
        "external_order_id_idempotency": idempotency_key,
    }
    try:
        r = httpx.post(f"{_BASE}/invoices", json=body, headers=_headers(), timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        log.warning("apipay create_invoice network: %s", exc)
        raise PaymentUnavailable("Платёжный шлюз недоступен, попробуйте позже") from exc
    if r.status_code == 409:                         # идемпотентность: тот же заказ
        return r.json()
    if r.status_code >= 400:
        data = _safe_json(r)
        log.warning("apipay create_invoice %s: %s", r.status_code, data.get("error_code"))
        raise PaymentUnavailable(data.get("message") or "Не удалось создать счёт Kaspi")
    return r.json()


def invoice_status(invoice_id: str | int) -> dict:
    """Опросить статус инвойса (fallback к вебхуку)."""
    if not is_configured():
        raise PaymentUnavailable("APIPAY_API_KEY не задан")
    try:
        r = httpx.get(f"{_BASE}/invoices/{invoice_id}", headers=_headers(), timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise PaymentUnavailable("Платёжный шлюз недоступен") from exc
    if r.status_code >= 400:
        raise PaymentUnavailable("Инвойс не найден")
    return r.json()


def refund(invoice_id: str | int, amount: int | None = None,
           reason: str = "Возврат заказа") -> dict:
    """Полный (amount=None) или частичный возврат по инвойсу."""
    if not is_configured():
        raise PaymentUnavailable("APIPAY_API_KEY не задан")
    body: dict = {"reason": reason}
    if amount is not None:
        body["amount"] = float(amount)
    try:
        r = httpx.post(f"{_BASE}/invoices/{invoice_id}/refund", json=body,
                       headers=_headers(), timeout=_TIMEOUT)
    except httpx.HTTPError as exc:
        raise PaymentUnavailable("Платёжный шлюз недоступен") from exc
    if r.status_code >= 400:
        data = _safe_json(r)
        raise PaymentUnavailable(data.get("message") or "Возврат не выполнен")
    return r.json()


def verify_webhook(raw_body: bytes, signature_header: str) -> bool:
    """Проверка подписи вебхука: HMAC-SHA256 сырого тела с webhook-секретом.
    Заголовок X-Webhook-Signature вида 'sha256=<hex>'. Секрет не задан → False
    (вебхук без проверки не обрабатываем — безопасность важнее удобства)."""
    secret = _webhook_secret()
    if not secret or not signature_header:
        return False
    provided = signature_header.split("=", 1)[-1].strip()
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, provided)


def _safe_json(r: httpx.Response) -> dict:
    try:
        return r.json()
    except Exception:                                # noqa: BLE001
        return {}
