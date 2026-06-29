"""Тесты бизнес-логики MVP: бронь, выдача, no-show, возврат, метрики."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import Store
from app.models import BoxCreate


@pytest.fixture
def store(tmp_path):
    s = Store(path=tmp_path / "t.db")
    s.upsert_partner_seed = None
    from app.models import Partner
    s.upsert_partner(Partner(id="p1", name="Кафе", district="Центр", address="ул. 1"))
    return s


def _box(store, qty=3, hours_ahead=4, price=900, value=2500):
    now = datetime.now(timezone.utc)
    return store.create_box("b1", BoxCreate(
        partner_id="p1", category="sweet", title="Box", price=price, value_est=value,
        qty=qty, pickup_from=(now - timedelta(minutes=10)).isoformat(),
        pickup_to=(now + timedelta(hours=hours_ahead)).isoformat(),
    ))


def test_discount_computed(store):
    b = _box(store, price=900, value=2500)
    assert b.discount == 64  # round((1-900/2500)*100)


def test_booking_decrements_qty(store):
    _box(store, qty=3)
    o = store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    assert o is not None
    assert store.box("b1").qty_left == 2


def test_cannot_book_when_empty(store):
    _box(store, qty=1)
    store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    # бокс закончился — повторная бронь возвращает None
    assert store.create_order("o2", "SB-BBBB", store.box("b1"), "Имя2", "+771") is None


def test_redeem_issues_then_blocks_double(store):
    _box(store)
    store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    ok, msg, order = store.redeem("sb-aaaa")          # код регистронезависимый
    assert ok and order.status == "issued"
    ok2, msg2, _ = store.redeem("SB-AAAA")
    assert not ok2 and "уже выдан" in msg2


def test_no_show_when_window_passed(store):
    # окно выдачи уже истекло
    now = datetime.now(timezone.utc)
    store.create_box("b1", BoxCreate(
        partner_id="p1", category="sweet", title="Box", price=900, value_est=2500,
        qty=2, pickup_from=(now - timedelta(hours=3)).isoformat(),
        pickup_to=(now - timedelta(hours=1)).isoformat(),
    ))
    store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    order = store.order_by_code("SB-AAAA")
    assert order.status == "expired"                  # no-show
    ok, msg, _ = store.redeem("SB-AAAA")
    assert not ok and "истекло" in msg.lower()


def test_refund_returns_box_and_excludes_gmv(store):
    _box(store, qty=2, price=900)
    o = store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    assert store.box("b1").qty_left == 1
    assert store.refund(o.id) is True
    assert store.box("b1").qty_left == 2              # бокс вернулся в наличие
    stats = store.stats()
    assert stats["refunds"] == 1
    assert stats["gmv"] == 0                          # возврат не в обороте


def test_stats_fill_rate(store):
    _box(store, qty=5)
    for i in range(3):
        store.create_order(f"o{i}", f"SB-{i:04d}", store.box("b1"), "Имя", "+770")
    store.redeem("SB-0000")                            # 1 из 3 выдан
    stats = store.stats()
    assert stats["orders_total"] == 3
    assert stats["issued"] == 1
    assert stats["fill_rate"] == 33
