"""Движок комиссий: мерчант-аккаунты, целочисленный расчёт, ledger, сторно."""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import pytest
from app.db import Store
from app.models import BoxCreate, Partner


@pytest.fixture
def store(tmp_path):
    s = Store(path=tmp_path / "t.db")
    s.upsert_partner(Partner(id="p1", name="Coffee Point", district="Ц", address="ул.1"))
    return s


def _box(store, price=1000, value=2500):
    now = datetime.now(timezone.utc)
    return store.create_box("b1", BoxCreate(
        partner_id="p1", category="sweet", title="Box", price=price, value_est=value,
        qty=5, pickup_from=(now - timedelta(minutes=5)).isoformat(),
        pickup_to=(now + timedelta(hours=3)).isoformat()))


def test_commission_math_integer_roundup():
    # 1000 ₸ = 100000 тиын, 10% = 10000; 990 ₸ * 7.5% → округление вверх
    assert Store.commission_minor(100_000, 1000) == 10_000
    assert Store.commission_minor(99_000, 750) == 7_425   # ровно
    assert Store.commission_minor(1, 1000) == 1           # округление вверх, не 0


def test_no_accrual_without_active_account(store):
    _box(store)
    o = store.create_order("o1", "YM-A", store.box("b1"), "Т", "+7700")
    assert store.accrue_commission("cl1", o) is None       # аккаунта нет
    assert store.commission_summary("p1")["owed_minor"] == 0


def test_accrual_and_reversal(store):
    store.upsert_payment_account("pa1", "p1", "pub1", "KASPI-ИП-МАМЫ")
    store.set_payment_account_status("p1", "active", payments_enabled=True)
    assert store.can_sell_paid("p1") is True
    _box(store, price=1000)
    o = store.create_order("o1", "YM-A", store.box("b1"), "Т", "+7700")
    e = store.accrue_commission("cl1", o)
    assert e["commission_minor"] == 10_000 and e["rate_bps"] == 1000  # 10% от 1000₸
    assert store.commission_summary("p1")["owed_tenge"] == 100
    # одна запись на заказ
    assert store.accrue_commission("cl2", o) is None
    # сторно
    assert store.reverse_commission("o1") is True
    assert store.commission_summary("p1")["owed_minor"] == 0
    assert store.reverse_commission("o1") is False          # повторно нельзя


def test_custom_commission_rate(store):
    store.upsert_payment_account("pa1", "p1", "pub1", "M")
    store.set_payment_account_status("p1", "active", payments_enabled=True)
    store.set_commission_rate("cr1", "p1", 750)             # 7.5%
    assert store.active_commission_bps("p1") == 750
    _box(store, price=1000)
    o = store.create_order("o1", "YM-A", store.box("b1"), "Т", "+7700")
    e = store.accrue_commission("cl1", o)
    assert e["commission_minor"] == 7_500                   # 7.5% от 1000₸


def test_can_sell_paid_requires_active_and_enabled(store):
    assert store.can_sell_paid("p1") is False
    store.upsert_payment_account("pa1", "p1", "pub1", "M")
    assert store.can_sell_paid("p1") is False               # pending
    store.set_payment_account_status("p1", "active", payments_enabled=True)
    assert store.can_sell_paid("p1") is True
    store.set_payment_account_status("p1", "suspended", payments_enabled=False)
    assert store.can_sell_paid("p1") is False
