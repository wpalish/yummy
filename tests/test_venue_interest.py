"""«Кого зовут» — спрос покупателей на заведения с карты.

Заменяет фейковую бронь: вместо выдуманного QR от имени реальной кофейни
копим честный сигнал «сюда хотят боксы» → очередь на подключение.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.accounts import Accounts
from app.db import Store


@pytest.fixture
def c(tmp_path, monkeypatch):
    import app.accounts as accounts_mod

    monkeypatch.setattr(accounts_mod, "_ADMIN_EMAILS", {"boss@yummy.kz"})
    monkeypatch.setattr(accounts_mod, "_ENFORCE", True)
    monkeypatch.setattr(accounts_mod, "accounts", Accounts(path=tmp_path / "u.db"))
    monkeypatch.setattr(main_mod, "store", Store(path=tmp_path / "s.db"))
    accounts_mod._auth_hits.clear()
    accounts_mod._jail.clear()
    main_mod._rate_hits.clear()
    return TestClient(main_mod.app)


def _vote(c, vid="70000001112351659", name="Espresso Day"):
    return c.post("/venues/interest", json={
        "venue_id": vid, "name": name,
        "address": "Бухар жырау, 26/1", "district": "Есильский"})


def _admin(c) -> dict:
    r = c.post("/auth/register", json={"email": "boss@yummy.kz", "password": "Secret123"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


# --------------------------------------------------------------------------- #
#  Голос за заведение
# --------------------------------------------------------------------------- #
def test_vote_counts_up(c):
    assert _vote(c).json()["votes"] == 1
    assert _vote(c).json()["votes"] == 2          # копится по тому же заведению


def test_votes_are_per_venue(c):
    _vote(c, "v1", "Zebra Coffee")
    _vote(c, "v1", "Zebra Coffee")
    assert _vote(c, "v2", "Espresso Day").json()["votes"] == 1


def test_vote_stores_no_personal_data(c):
    """В таблице только заведение и счётчик — никаких IP/имён покупателей."""
    _vote(c)
    rows = main_mod.store.venue_interest_top()
    assert set(rows[0]) == {"venue_id", "name", "address", "district", "votes", "updated_at"}


def test_vote_validates_input(c):
    assert c.post("/venues/interest", json={"venue_id": "", "name": "X"}).status_code == 422
    assert c.post("/venues/interest", json={"venue_id": "v1"}).status_code == 422


# --------------------------------------------------------------------------- #
#  Админский список
# --------------------------------------------------------------------------- #
def test_top_sorted_by_votes(c):
    for _ in range(3):
        _vote(c, "v1", "Популярная")
    _vote(c, "v2", "Одинокая")
    rows = c.get("/admin/venue-interest", headers=_admin(c)).json()
    assert [r["name"] for r in rows] == ["Популярная", "Одинокая"]
    assert rows[0]["votes"] == 3


def test_interest_list_requires_admin(c):
    _vote(c)
    r = c.post("/auth/register", json={"email": "buyer@x.kz", "password": "Secret123"})
    buyer = {"Authorization": f"Bearer {r.json()['access_token']}"}
    assert c.get("/admin/venue-interest", headers=buyer).status_code == 403
    assert c.get("/admin/venue-interest").status_code == 401


def test_empty_when_no_votes(c):
    assert c.get("/admin/venue-interest", headers=_admin(c)).json() == []
