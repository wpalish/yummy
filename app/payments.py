"""Stripe Checkout adapter. Business state remains authoritative in PostgreSQL."""
from __future__ import annotations

import os
from typing import Any

import stripe

_MODE = os.getenv("YUMMY_PAYMENT_MODE", "demo").lower()
_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
_PUBLIC_URL = os.getenv("YUMMY_PUBLIC_URL", "http://localhost:8021").rstrip("/")
_CURRENCY = os.getenv("STRIPE_CURRENCY", "kzt").lower()


class PaymentUnavailable(RuntimeError):
    pass


def payment_mode() -> str:
    return _MODE


def assert_payment_config(production: bool) -> None:
    if _MODE not in {"demo", "disabled", "stripe"}:
        raise RuntimeError("YUMMY_PAYMENT_MODE должен быть demo, disabled или stripe")
    if production and _MODE == "demo":
        raise RuntimeError("production запрещает demo payment mode")
    if _MODE == "stripe" and (
        not _SECRET_KEY.startswith(("sk_test_", "sk_live_"))
        or not _WEBHOOK_SECRET.startswith("whsec_")
        or (production and not _PUBLIC_URL.startswith("https://"))
    ):
        raise RuntimeError("Stripe mode требует secret/webhook keys и HTTPS YUMMY_PUBLIC_URL")
    if production and _MODE == "stripe" and _SECRET_KEY.startswith("sk_test_"):
        raise RuntimeError("production Stripe mode не принимает test secret key")


class StripeGateway:
    def create_checkout(self, *, payment_id: str, order_id: str, title: str,
                        amount_minor: int, currency: str, idempotency_key: str) -> dict:
        if _MODE != "stripe":
            raise PaymentUnavailable("Stripe payment mode выключен")
        stripe.api_key = _SECRET_KEY
        try:
            session = stripe.checkout.Session.create(
                mode="payment",
                line_items=[{"price_data": {
                    "currency": currency, "unit_amount": amount_minor,
                    "product_data": {"name": title},
                }, "quantity": 1}],
                client_reference_id=order_id,
                metadata={"order_id": order_id, "payment_id": payment_id},
                success_url=f"{_PUBLIC_URL}/?payment=success&session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{_PUBLIC_URL}/?payment=cancelled",
                idempotency_key=idempotency_key,
            )
        except stripe.StripeError as exc:
            raise PaymentUnavailable("Stripe Checkout недоступен") from exc
        return {"id": session.id, "url": session.url}

    def retrieve_checkout(self, session_id: str) -> dict[str, Any]:
        if _MODE != "stripe":
            raise PaymentUnavailable("Stripe payment mode выключен")
        stripe.api_key = _SECRET_KEY
        try:
            return dict(stripe.checkout.Session.retrieve(session_id))
        except stripe.StripeError as exc:
            raise PaymentUnavailable("Stripe reconciliation недоступен") from exc

    def construct_event(self, payload: bytes, signature: str) -> dict[str, Any]:
        if not _WEBHOOK_SECRET:
            raise PaymentUnavailable("Stripe webhook secret не настроен")
        try:
            event = stripe.Webhook.construct_event(payload, signature, _WEBHOOK_SECRET)
        except (ValueError, stripe.SignatureVerificationError) as exc:
            raise PaymentUnavailable("Некорректная Stripe webhook подпись") from exc
        return dict(event)


gateway = StripeGateway()
