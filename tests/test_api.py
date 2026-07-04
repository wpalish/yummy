"""API endpoint tests for app/main.py — covers all routes."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import patch, PropertyMock

import pytest
from fastapi.testclient import TestClient

from app.db import Store
from app.models import BoxCreate, Partner


@pytest.fixture(autouse=True)
def _patch_store(tmp_path):
    """Replace the global ``store`` with a fresh in-memory instance per test."""
    s = Store(path=tmp_path / "api.db")
    with patch("app.main.store", s):
        yield s


@pytest.fixture
def client():
    from app.main import app
    return TestClient(app)


@pytest.fixture
def seeded(client, _patch_store):
    """Seed a partner and an available box, return (store, partner_id, box_id)."""
    s = _patch_store
    s.upsert_partner(Partner(id="p1", name="Кафе", district="Центр", address="ул. 1"))
    now = datetime.now(timezone.utc)
    s.create_box("b1", BoxCreate(
        partner_id="p1", category="sweet", title="Test Box", price=900, value_est=2500,
        qty=5, pickup_from=(now - timedelta(minutes=10)).isoformat(),
        pickup_to=(now + timedelta(hours=4)).isoformat(),
    ))
    return s, "p1", "b1"


# ------------------------------------------------------------------ #
#  Страница / служебное
# ------------------------------------------------------------------ #
class TestHealth:
    def test_health_ok(self, client, seeded):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert body["partners"] >= 1


class TestIndex:
    def test_index_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200


# ------------------------------------------------------------------ #
#  Магазин (покупатель)
# ------------------------------------------------------------------ #
class TestDistricts:
    def test_districts_returns_list(self, client, seeded):
        r = client.get("/districts")
        assert r.status_code == 200
        assert "Центр" in r.json()


class TestListBoxes:
    def test_list_boxes_all(self, client, seeded):
        r = client.get("/boxes")
        assert r.status_code == 200
        assert len(r.json()) >= 1

    def test_list_boxes_filter_district(self, client, seeded):
        r = client.get("/boxes", params={"district": "Центр"})
        assert r.status_code == 200
        assert all(b["district"] == "Центр" for b in r.json())

    def test_list_boxes_filter_nonexistent_district(self, client, seeded):
        r = client.get("/boxes", params={"district": "Нигде"})
        assert r.status_code == 200
        assert r.json() == []


class TestGetBox:
    def test_get_existing_box(self, client, seeded):
        r = client.get("/boxes/b1")
        assert r.status_code == 200
        assert r.json()["id"] == "b1"

    def test_get_missing_box_404(self, client):
        r = client.get("/boxes/nonexistent")
        assert r.status_code == 404


class TestCreateOrder:
    def test_create_order_success(self, client, seeded):
        r = client.post("/orders", json={
            "box_id": "b1", "user_name": "Алиса", "user_phone": "+77001234567",
        })
        assert r.status_code == 201
        body = r.json()
        assert "order" in body
        assert "qr_svg" in body
        assert body["order"]["status"] == "paid"
        assert body["order"]["code"].startswith("SB-")

    def test_create_order_box_not_found(self, client, seeded):
        r = client.post("/orders", json={
            "box_id": "missing", "user_name": "Алиса", "user_phone": "+77001234567",
        })
        assert r.status_code == 404

    def test_create_order_out_of_stock(self, client, _patch_store):
        s = _patch_store
        s.upsert_partner(Partner(id="p1", name="Кафе", district="Центр", address="ул. 1"))
        now = datetime.now(timezone.utc)
        s.create_box("b1", BoxCreate(
            partner_id="p1", category="sweet", title="Box", price=900, value_est=2500,
            qty=1, pickup_from=(now - timedelta(minutes=10)).isoformat(),
            pickup_to=(now + timedelta(hours=4)).isoformat(),
        ))
        # book the only box
        client.post("/orders", json={
            "box_id": "b1", "user_name": "Алиса", "user_phone": "+77001234567",
        })
        r = client.post("/orders", json={
            "box_id": "b1", "user_name": "Борис", "user_phone": "+77007654321",
        })
        assert r.status_code == 409


class TestOrderStatus:
    def test_order_status_by_code(self, client, seeded):
        r = client.post("/orders", json={
            "box_id": "b1", "user_name": "Алиса", "user_phone": "+77001234567",
        })
        code = r.json()["order"]["code"]
        r2 = client.get(f"/orders/{code}")
        assert r2.status_code == 200
        assert r2.json()["code"] == code

    def test_order_status_not_found(self, client):
        r = client.get("/orders/SB-NOPE")
        assert r.status_code == 404


# ------------------------------------------------------------------ #
#  Кабинет партнёра
# ------------------------------------------------------------------ #
class TestPartners:
    def test_list_partners(self, client, seeded):
        r = client.get("/partners")
        assert r.status_code == 200
        assert len(r.json()) >= 1


class TestCreateBox:
    def test_create_box_endpoint(self, client, seeded):
        now = datetime.now(timezone.utc)
        r = client.post("/boxes", json={
            "partner_id": "p1", "category": "bakery", "title": "New Box",
            "price": 800, "value_est": 2000, "qty": 3,
            "pickup_from": (now - timedelta(minutes=10)).isoformat(),
            "pickup_to": (now + timedelta(hours=4)).isoformat(),
        })
        assert r.status_code == 201
        assert r.json()["title"] == "New Box"

    def test_create_box_value_less_than_price_rejected(self, client, seeded):
        now = datetime.now(timezone.utc)
        r = client.post("/boxes", json={
            "partner_id": "p1", "category": "sweet", "title": "Bad Box",
            "price": 5000, "value_est": 1000, "qty": 1,
            "pickup_from": (now - timedelta(minutes=10)).isoformat(),
            "pickup_to": (now + timedelta(hours=4)).isoformat(),
        })
        assert r.status_code == 400


class TestPartnerBoxes:
    def test_partner_boxes(self, client, seeded):
        r = client.get("/partners/p1/boxes")
        assert r.status_code == 200
        assert len(r.json()) >= 1


class TestPartnerOrders:
    def test_partner_orders(self, client, seeded):
        client.post("/orders", json={
            "box_id": "b1", "user_name": "Алиса", "user_phone": "+77001234567",
        })
        r = client.get("/partners/p1/orders")
        assert r.status_code == 200
        assert len(r.json()) >= 1


class TestRedeem:
    def test_redeem_success(self, client, seeded):
        r = client.post("/orders", json={
            "box_id": "b1", "user_name": "Алиса", "user_phone": "+77001234567",
        })
        code = r.json()["order"]["code"]
        r2 = client.post("/redeem", json={"code": code})
        assert r2.status_code == 200
        assert r2.json()["ok"] is True
        assert r2.json()["order"]["status"] == "issued"

    def test_redeem_not_found(self, client):
        r = client.post("/redeem", json={"code": "SB-XXXX"})
        assert r.status_code == 200
        assert r.json()["ok"] is False


# ------------------------------------------------------------------ #
#  Админка
# ------------------------------------------------------------------ #
class TestAdminStats:
    def test_admin_stats(self, client, seeded):
        r = client.get("/admin/stats")
        assert r.status_code == 200
        assert "gmv" in r.json()


class TestAdminOrders:
    def test_admin_orders(self, client, seeded):
        r = client.get("/admin/orders")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestAdminRefund:
    def test_refund_success(self, client, seeded):
        r = client.post("/orders", json={
            "box_id": "b1", "user_name": "Алиса", "user_phone": "+77001234567",
        })
        order_id = r.json()["order"]["id"]
        r2 = client.post(f"/admin/refund/{order_id}")
        assert r2.status_code == 200
        assert r2.json()["refunded"] is True

    def test_refund_nonexistent(self, client):
        r = client.post("/admin/refund/fake-id")
        assert r.status_code == 200
        assert r.json()["refunded"] is False


class TestReseed:
    def test_reseed(self, client):
        r = client.post("/admin/seed")
        assert r.status_code == 200
        body = r.json()
        assert body["partners"] > 0
        assert body["boxes"] > 0


class TestLocalOnly:
    def test_local_only_allows_testclient(self, client):
        r = client.post("/admin/seed")
        assert r.status_code == 200

    def test_local_only_rejects_external(self, client):
        """Simulate a non-local request by patching client.host."""
        from app.main import local_only
        from unittest.mock import MagicMock
        from fastapi import HTTPException
        req = MagicMock()
        req.client.host = "8.8.8.8"
        with pytest.raises(HTTPException) as exc_info:
            local_only(req)
        assert exc_info.value.status_code == 403


class TestLifespan:
    def test_lifespan_seeds_empty_db(self, _patch_store):
        """When the store is empty the lifespan auto-seeds."""
        import asyncio
        from app.main import app, lifespan

        s = _patch_store
        assert s.count() == (0, 0, 0)

        async def _run():
            async with lifespan(app):
                pass

        asyncio.get_event_loop().run_until_complete(_run())
        p, b, o = s.count()
        assert p > 0 and b > 0


class TestCreateOrderRace:
    def test_race_condition_returns_409(self, client, _patch_store):
        """Cover the race-condition path where _take_one fails after qty check."""
        s = _patch_store
        s.upsert_partner(Partner(id="p1", name="Кафе", district="Центр", address="ул. 1"))
        now = datetime.now(timezone.utc)
        s.create_box("b1", BoxCreate(
            partner_id="p1", category="sweet", title="Box", price=900, value_est=2500,
            qty=1, pickup_from=(now - timedelta(minutes=10)).isoformat(),
            pickup_to=(now + timedelta(hours=4)).isoformat(),
        ))
        original_create_order = s.create_order

        def _return_none(*args, **kwargs):
            return None

        with patch.object(s, "create_order", side_effect=_return_none):
            r = client.post("/orders", json={
                "box_id": "b1", "user_name": "Алиса", "user_phone": "+77001234567",
            })
            assert r.status_code == 409
