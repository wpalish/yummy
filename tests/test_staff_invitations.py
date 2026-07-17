"""Доступ к партнёрке/админке — только по одноразовому инвайту от админа.

Портировано с arena-ветки на архитектуру main (сырой SQL, без Alembic).
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app import main as main_mod
from app.accounts import Accounts
from app.db import Store
from app.models import Partner


@pytest.fixture
def c(tmp_path, monkeypatch):
    import app.accounts as accounts_mod

    # allowlist админов читается на импорте — подменяем сам объект
    monkeypatch.setattr(accounts_mod, "_ADMIN_EMAILS", {"boss@yummy.kz"})
    # включаем реальную проверку ролей (иначе демо-режим пускает всех)
    monkeypatch.setattr(accounts_mod, "_ENFORCE", True)
    monkeypatch.setattr(accounts_mod, "accounts", Accounts(path=tmp_path / "u.db"))
    store = Store(path=tmp_path / "t.db")
    store.upsert_partner(Partner(id="p1", name="Coffee Point",
                                 district="Есильский р-н", address="пр. Мангилик Ел, 55"))
    monkeypatch.setattr(main_mod, "store", store)
    # изоляция: rate-limit/jail общие по IP — иначе 429 при быстром прогоне
    accounts_mod._auth_hits.clear()
    accounts_mod._jail.clear()
    main_mod._rate_hits.clear()
    main_mod._ai_hits.clear()
    return TestClient(main_mod.app)


def _admin_token(c) -> str:
    r = c.post("/auth/register", json={"email": "boss@yummy.kz", "password": "Secret123"})
    assert r.status_code == 201 and r.json()["user"]["role"] == "admin"
    return r.json()["access_token"]


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


# --------------------------------------------------------------------------- #
#  Выдача инвайта — только админ
# --------------------------------------------------------------------------- #
def test_invite_requires_admin(c):
    r = c.post("/auth/register", json={"email": "buyer@yummy.kz", "password": "Secret123"})
    buyer = r.json()["access_token"]
    resp = c.post("/admin/staff-invitations",
                  json={"email": "new@cafe.kz", "partner_role": "owner",
                        "brand_name": "Bake House"},
                  headers=_h(buyer))
    assert resp.status_code in (401, 403)   # покупатель не может звать персонал


def test_admin_creates_owner_invite_and_link(c):
    tok = _admin_token(c)
    r = c.post("/admin/staff-invitations",
               json={"email": "owner@cafe.kz", "partner_role": "owner",
                     "brand_name": "Bake House", "address": "ул. Абая, 1"},
               headers=_h(tok))
    assert r.status_code == 201
    url = r.json()["invite_url"]
    assert "?invite=" in url and len(url.split("?invite=")[1]) > 20


def test_owner_invite_needs_brand(c):
    tok = _admin_token(c)
    r = c.post("/admin/staff-invitations",
               json={"email": "owner@cafe.kz", "partner_role": "owner"},
               headers=_h(tok))
    assert r.status_code == 422


def test_staff_invite_needs_existing_partner(c):
    tok = _admin_token(c)
    r = c.post("/admin/staff-invitations",
               json={"email": "cashier@cafe.kz", "partner_role": "cashier",
                     "partner_id": "nope"},
               headers=_h(tok))
    assert r.status_code == 404


# --------------------------------------------------------------------------- #
#  Приём инвайта
# --------------------------------------------------------------------------- #
def _invite(c, tok, **kw) -> str:
    body = {"email": "owner@cafe.kz", "partner_role": "owner", "brand_name": "Bake House"}
    body.update(kw)
    r = c.post("/admin/staff-invitations", json=body, headers=_h(tok))
    assert r.status_code == 201
    return r.json()["invite_url"].split("?invite=")[1]


def test_accept_invite_creates_partner(c):
    raw = _invite(c, _admin_token(c))
    prev = c.get(f"/auth/invite/{raw}")
    assert prev.status_code == 200 and prev.json()["partner_role"] == "owner"
    r = c.post("/auth/accept-invite", json={"token": raw, "password": "Secret123"})
    assert r.status_code == 201
    u = r.json()["user"]
    assert u["role"] == "partner" and u["partner_role"] == "owner" and u["partner_id"]


def test_invite_is_single_use(c):
    raw = _invite(c, _admin_token(c))
    assert c.post("/auth/accept-invite", json={"token": raw, "password": "Secret123"}).status_code == 201
    again = c.post("/auth/accept-invite", json={"token": raw, "password": "Secret123"})
    assert again.status_code == 404          # повторно — нельзя


def test_bad_token_rejected(c):
    r = c.post("/auth/accept-invite", json={"token": "garbage", "password": "Secret123"})
    assert r.status_code == 404
    assert c.get("/auth/invite/garbage").status_code == 404


def test_expired_invite_rejected(c, monkeypatch):
    tok = _admin_token(c)
    from app.accounts import accounts as users
    raw = users.issue_staff_invitation(email="late@cafe.kz", partner_id=None,
                                       partner_role="owner", invited_by="admin",
                                       brand_name="Late Cafe", ttl=-1)
    assert users.peek_invitation(raw) is None
    r = c.post("/auth/accept-invite", json={"token": raw, "password": "Secret123"})
    assert r.status_code == 404


def test_token_stored_hashed_not_raw(c):
    from app.accounts import accounts as users
    raw = users.issue_staff_invitation(email="h@cafe.kz", partner_id=None,
                                       partner_role="owner", invited_by="admin",
                                       brand_name="Hash Cafe")
    with users._conn() as conn:
        rows = conn.execute("SELECT token_hash FROM staff_invitations").fetchall()
    assert all(r["token_hash"] != raw for r in rows)   # сырой токен в БД не лежит
