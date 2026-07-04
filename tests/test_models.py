"""Tests for app/models.py — computed fields and edge cases."""
from __future__ import annotations

from app.models import (
    CATEGORY_EMOJI,
    CATEGORY_RU,
    Box,
    Order,
    _utcnow,
)


def _box(**overrides):
    defaults = dict(
        id="b1", partner_id="p1", partner_name="Кафе", district="Центр",
        address="ул. 1", rating=4.7, category="sweet", title="Box",
        price=900, value_est=2500, qty_total=5, qty_left=5,
        pickup_from="2025-01-01T18:00:00+00:00",
        pickup_to="2025-01-01T22:00:00+00:00", description="",
    )
    defaults.update(overrides)
    return Box(**defaults)


def test_discount_normal():
    b = _box(price=900, value_est=2500)
    assert b.discount == 64


def test_discount_zero_value():
    b = _box(price=900, value_est=0)
    assert b.discount == 0


def test_discount_equal_price_and_value():
    b = _box(price=1000, value_est=1000)
    assert b.discount == 0


def test_category_ru_known():
    for cat, label in CATEGORY_RU.items():
        b = _box(category=cat)
        assert b.category_ru == label


def test_emoji_known():
    for cat, emoji in CATEGORY_EMOJI.items():
        b = _box(category=cat)
        assert b.emoji == emoji


def test_order_category_ru_and_emoji():
    o = Order(
        id="o1", code="SB-AAAA", box_id="b1", partner_id="p1",
        partner_name="Кафе", address="ул. 1", category="bakery",
        price=900, user_name="Имя", user_phone="+770",
        status="paid", pickup_from="2025-01-01T18:00:00+00:00",
        pickup_to="2025-01-01T22:00:00+00:00",
    )
    assert o.category_ru == "Bakery Box"
    assert o.emoji == "🥐"


def test_utcnow_returns_aware_datetime():
    dt = _utcnow()
    assert dt.tzinfo is not None
