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


def test_order_binds_user_and_user_orders(store):
    box = _box(store)
    store.create_order("o_u1", "YM-USER", box, "Т", "+7700", user_id="u42")
    mine = store.user_orders("u42")
    assert len(mine) == 1 and mine[0].id == "o_u1"
    assert store.user_orders("nobody") == []


# ---- отзывы (только по issued-заказу, одна ревью на заказ) ------------------ #
def test_review_requires_no_prior_review(store):
    box = _box(store)
    order = store.create_order("o1", "YM-REV1", box, "Т", "+7700", user_id="u1")
    store.redeem("YM-REV1")  # issued
    assert store.has_review(order.id) is False
    r = store.create_review("rv1", "p1", order.id, "u1", "Т", 5, "Отлично!", "approved")
    assert r.rating == 5 and r.status == "approved"
    assert store.has_review(order.id) is True


def test_partner_reviews_only_approved(store):
    box = _box(store, qty=2)
    o1 = store.create_order("o1", "YM-A", box, "А", "+7700", user_id="u1")
    store.redeem("YM-A")
    store.create_review("rv1", "p1", o1.id, "u1", "А", 5, "Хорошо", "approved")
    o2 = store.create_order("o2", "YM-B", box, "Б", "+7700", user_id="u2")
    store.redeem("YM-B")
    store.create_review("rv2", "p1", o2.id, "u2", "Б", 1, "Спам", "rejected", "спам")
    visible = store.partner_reviews("p1")
    assert len(visible) == 1 and visible[0].id == "rv1"


# ---- рекомендации (без AI: частота категории/заведения) --------------------- #
def test_recommend_boxes_no_history_returns_soonest(store):
    _box(store, hours_ahead=1)
    recs = store.recommend_boxes("nobody")
    assert len(recs) == 1


def test_recommend_boxes_prefers_ordered_category(tmp_path):
    from app.models import BoxCreate, Partner
    s = Store(path=tmp_path / "rec.db")
    s.upsert_partner(Partner(id="p1", name="Кафе А", district="Центр", address="ул. 1"))
    now = datetime.now(timezone.utc)

    def mk(bid, cat, pid="p1"):
        return s.create_box(bid, BoxCreate(
            partner_id=pid, category=cat, title="x", price=900, value_est=2000, qty=3,
            pickup_from=(now - timedelta(minutes=5)).isoformat(),
            pickup_to=(now + timedelta(hours=3)).isoformat(),
        ))

    sweet = mk("b1", "sweet")
    mk("b2", "snack")
    order = s.create_order("o1", "YM-X", sweet, "Т", "+7700", user_id="u1")
    s.redeem("YM-X")
    recs = s.recommend_boxes("u1")
    assert recs[0].category == "sweet"  # тот же вкус, что уже заказывал


# --------------------------------------------------------------------------- #
#  Отмена брони покупателем и возврат по коду (самообслуживание)
# --------------------------------------------------------------------------- #
def _future_box(store, bid="bf1", minutes_ahead=30):
    now = datetime.now(timezone.utc)
    return store.create_box(bid, BoxCreate(
        partner_id="p1", category="sweet", title="Box", price=900, value_est=2500,
        qty=3, pickup_from=(now + timedelta(minutes=minutes_ahead)).isoformat(),
        pickup_to=(now + timedelta(hours=4)).isoformat(),
    ))


def test_cancel_before_window_returns_box(store):
    box = _future_box(store)
    store.create_order("o1", "YM-CNL1", box, "Т", "+7700")
    assert store.box("bf1").qty_left == 2
    ok, msg = store.cancel_order("ym-cnl1")  # регистр не важен
    assert ok and "отменена" in msg
    assert store.box("bf1").qty_left == 3          # бокс вернулся в продажу
    assert store.order_by_code("YM-CNL1").status == "cancelled"
    ok2, _ = store.cancel_order("YM-CNL1")         # повторная отмена блокируется
    assert not ok2


def test_cancel_after_window_start_blocked(store):
    _box(store)  # окно началось 10 минут назад
    store.create_order("o1", "YM-CNL2", store.box("b1"), "Т", "+7700")
    ok, msg = store.cancel_order("YM-CNL2")
    assert not ok and "уже началось" in msg


def test_refund_by_code_after_window_start(store):
    _box(store)
    store.create_order("o1", "YM-RFD1", store.box("b1"), "Т", "+7700")
    left_before = store.box("b1").qty_left
    ok, msg = store.refund_by_code("YM-RFD1")
    assert ok and "Возврат" in msg
    assert store.order_by_code("YM-RFD1").status == "refunded"
    assert store.box("b1").qty_left == left_before + 1


def test_refund_by_code_before_window_blocked(store):
    box = _future_box(store)
    store.create_order("o1", "YM-RFD2", box, "Т", "+7700")
    ok, msg = store.refund_by_code("YM-RFD2")
    assert not ok and "ещё не началось" in msg


def test_cancel_unknown_code(store):
    ok, msg = store.cancel_order("YM-NOPE")
    assert not ok and "не найден" in msg


def test_cancel_issued_order_blocked(store):
    _box(store)
    store.create_order("o1", "YM-ISS1", store.box("b1"), "Т", "+7700")
    store.redeem("YM-ISS1")
    ok, _ = store.cancel_order("YM-ISS1")
    assert not ok
    ok2, _ = store.refund_by_code("YM-ISS1")
    assert not ok2
