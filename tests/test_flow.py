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
    # DTO запрещает публиковать уже истёкшее окно. Для проверки перехода времени
    # создаём валидный заказ, затем сдвигаем сохранённое окно в прошлое.
    _box(store, qty=2)
    store.create_order("o1", "SB-AAAA", store.box("b1"), "Имя", "+770")
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with store._conn() as conn:
        conn.execute("UPDATE orders SET pickup_to=? WHERE id='o1'", (past,))
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


def test_stats_fill_rate_uses_only_closed_orders(store):
    _box(store, qty=5)
    for i in range(3):
        store.create_order(f"o{i}", f"SB-{i:04d}", store.box("b1"), "Имя", "+770")
    store.redeem("SB-0000")                            # 1 closed + 2 active
    stats = store.stats()
    assert stats["orders_total"] == 3
    assert stats["issued"] == 1
    assert stats["fill_rate"] == 100                   # active не занижают выкуп


def test_no_show_is_retained_in_gmv_and_fill_rate(store):
    _box(store, qty=3, price=900)
    for i in range(2):
        store.create_order(f"o{i}", f"SB-X{i}", store.box("b1"), "Имя", "+770")
    store.redeem("SB-X0")
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    with store._conn() as conn:
        conn.execute("UPDATE orders SET pickup_to=? WHERE id='o1'", (past,))
    stats = store.stats()
    assert stats["no_show"] == 1
    assert stats["gmv"] == 1800                        # no-show не возвращается
    assert stats["fill_rate"] == 50                    # 1 issued / 2 closed


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
    s.create_order("o1", "YM-X", sweet, "Т", "+7700", user_id="u1")
    s.redeem("YM-X")
    recs = s.recommend_boxes("u1")
    assert recs[0].category == "sweet"  # тот же вкус, что уже заказывал
