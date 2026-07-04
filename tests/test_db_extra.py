"""Extra db.Store tests for previously uncovered branches and methods."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.db import Store
from app.models import BoxCreate, Partner


@pytest.fixture
def store(tmp_path):
    s = Store(path=tmp_path / "t.db")
    s.upsert_partner(Partner(id="p1", name="Кафе", district="Центр", address="ул. 1"))
    return s


def _make_box(store, box_id="b1", qty=3, hours_ahead=4, price=900, value=2500):
    now = datetime.now(timezone.utc)
    return store.create_box(box_id, BoxCreate(
        partner_id="p1", category="sweet", title="Box", price=price, value_est=value,
        qty=qty, pickup_from=(now - timedelta(minutes=10)).isoformat(),
        pickup_to=(now + timedelta(hours=hours_ahead)).isoformat(),
    ))


# ------------------------------------------------------------------ #
#  partners()
# ------------------------------------------------------------------ #
def test_partners_list(store):
    partners = store.partners()
    assert len(partners) == 1
    assert partners[0].name == "Кафе"


# ------------------------------------------------------------------ #
#  boxes_available with district filter
# ------------------------------------------------------------------ #
def test_boxes_available_filter_all(store):
    _make_box(store)
    boxes = store.boxes_available(district="all")
    assert len(boxes) == 1


def test_boxes_available_filter_match(store):
    _make_box(store)
    boxes = store.boxes_available(district="Центр")
    assert len(boxes) == 1


def test_boxes_available_filter_no_match(store):
    _make_box(store)
    boxes = store.boxes_available(district="Другой")
    assert len(boxes) == 0


# ------------------------------------------------------------------ #
#  partner_boxes
# ------------------------------------------------------------------ #
def test_partner_boxes(store):
    _make_box(store, box_id="b1")
    _make_box(store, box_id="b2")
    boxes = store.partner_boxes("p1")
    assert len(boxes) == 2


def test_partner_boxes_empty(store):
    assert store.partner_boxes("p999") == []


# ------------------------------------------------------------------ #
#  orders / partner_orders
# ------------------------------------------------------------------ #
def test_orders_list(store):
    _make_box(store)
    store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    assert len(store.orders()) == 1


def test_partner_orders(store):
    _make_box(store)
    store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    assert len(store.partner_orders("p1")) == 1


def test_partner_orders_empty(store):
    assert store.partner_orders("p999") == []


# ------------------------------------------------------------------ #
#  order_by_code — not found
# ------------------------------------------------------------------ #
def test_order_by_code_missing(store):
    assert store.order_by_code("SB-ZZZZ") is None


# ------------------------------------------------------------------ #
#  _effective_status — ValueError path
# ------------------------------------------------------------------ #
def test_effective_status_invalid_date():
    assert Store._effective_status("paid", "not-a-date") == "paid"


def test_effective_status_future_pickup():
    future = (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat()
    assert Store._effective_status("paid", future) == "paid"


# ------------------------------------------------------------------ #
#  redeem — refunded / cancelled
# ------------------------------------------------------------------ #
def test_redeem_refunded_order(store):
    _make_box(store)
    store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    store.refund("o1")
    ok, msg, order = store.redeem("SB-AAAA")
    assert not ok
    assert order is not None


# ------------------------------------------------------------------ #
#  refund — already issued
# ------------------------------------------------------------------ #
def test_refund_already_issued(store):
    _make_box(store)
    store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    store.redeem("SB-AAAA")
    assert store.refund("o1") is False


def test_refund_nonexistent(store):
    assert store.refund("fake-id") is False


# ------------------------------------------------------------------ #
#  count
# ------------------------------------------------------------------ #
def test_count(store):
    p, b, o = store.count()
    assert p == 1
    assert b == 0
    assert o == 0


# ------------------------------------------------------------------ #
#  reset
# ------------------------------------------------------------------ #
def test_reset(store):
    _make_box(store)
    store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    store.reset()
    p, b, o = store.count()
    assert p == 0 and b == 0 and o == 0


# ------------------------------------------------------------------ #
#  stats — no_show and active branches
# ------------------------------------------------------------------ #
def test_stats_no_show(store):
    now = datetime.now(timezone.utc)
    store.create_box("b1", BoxCreate(
        partner_id="p1", category="sweet", title="Box", price=900, value_est=2500,
        qty=2, pickup_from=(now - timedelta(hours=3)).isoformat(),
        pickup_to=(now - timedelta(hours=1)).isoformat(),
    ))
    store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    stats = store.stats()
    assert stats["no_show"] == 1


def test_stats_active_order(store):
    _make_box(store)
    store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    stats = store.stats()
    assert stats["active"] == 1
    assert stats["gmv"] == 900
