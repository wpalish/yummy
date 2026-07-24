"""Ролевая защита эндпоинтов (API-Security-Checklist: «все эндпоинты за auth»).

Демо-режим (флаг выключен) — доступ открыт, как раньше. Прод-режим
(YUMMY_ENFORCE_AUTH=1) — нужен валидный JWT нужной роли.
"""
import pytest
from fastapi import HTTPException

import app.accounts as A


def test_demo_mode_open(monkeypatch):
    monkeypatch.setattr(A, "_ENFORCE", False)
    dep = A.require_role("admin")
    assert dep(authorization=None) is None  # без флага — открыто (демо работает)


def test_enforced_requires_token(monkeypatch):
    monkeypatch.setattr(A, "_ENFORCE", True)
    dep = A.require_role("admin")
    with pytest.raises(HTTPException) as exc:
        dep(authorization=None)
    assert exc.value.status_code == 401


def test_enforced_role_mismatch_403(tmp_path, monkeypatch):
    monkeypatch.setattr(A, "_ENFORCE", True)
    acc = A.Accounts(path=tmp_path / "e.db")
    monkeypatch.setattr(A, "accounts", acc)
    uid = acc.create("u@x.kz", A.hash_password("Secret123"), "customer", None, None)
    token = A.create_token(uid, "customer")

    # покупатель не проходит в admin-ручку
    with pytest.raises(HTTPException) as exc:
        A.require_role("admin")(authorization=f"Bearer {token}")
    assert exc.value.status_code == 403

    # своя роль — проходит
    user = A.require_role("customer", "admin")(authorization=f"Bearer {token}")
    assert user.role == "customer"


def test_owner_requires_2fa(tmp_path, monkeypatch):
    """Владелец заведения без включённой 2FA не проходит в partner-ручку;
    после включения TOTP — проходит. Персонал (cashier) 2FA не обязан."""
    monkeypatch.setattr(A, "_ENFORCE", True)
    monkeypatch.delenv("YUMMY_ADMIN_2FA_OPTIONAL", raising=False)
    acc = A.Accounts(path=tmp_path / "o.db")
    monkeypatch.setattr(A, "accounts", acc)

    owner = acc.create("owner@x.kz", A.hash_password("Secret123"), "partner",
                       "Coffee", "Astana", partner_id="p1", partner_role="owner")
    otoken = A.create_token(owner, "partner")

    # владелец без 2FA — 403 с требованием включить
    with pytest.raises(HTTPException) as exc:
        A.require_role("partner")(authorization=f"Bearer {otoken}")
    assert exc.value.status_code == 403
    assert "2FA" in exc.value.detail

    # включил 2FA — проходит
    from app import totp as totp_mod
    acc.set_totp(owner, totp_mod.new_secret())
    user = A.require_role("partner")(authorization=f"Bearer {otoken}")
    assert user.partner_role == "owner"

    # кассир (persona) без 2FA — проходит, 2FA не обязательна
    cash = acc.create("cash@x.kz", A.hash_password("Secret123"), "partner",
                      None, None, partner_id="p1", partner_role="cashier")
    ctoken = A.create_token(cash, "partner")
    u = A.require_role("partner")(authorization=f"Bearer {ctoken}")
    assert u.partner_role == "cashier"


def test_owner_2fa_optional_escape_hatch(tmp_path, monkeypatch):
    """YUMMY_ADMIN_2FA_OPTIONAL=1 снимает требование 2FA и с владельца."""
    monkeypatch.setattr(A, "_ENFORCE", True)
    monkeypatch.setenv("YUMMY_ADMIN_2FA_OPTIONAL", "1")
    acc = A.Accounts(path=tmp_path / "o2.db")
    monkeypatch.setattr(A, "accounts", acc)
    owner = acc.create("owner2@x.kz", A.hash_password("Secret123"), "partner",
                       "Coffee", "Astana", partner_id="p9", partner_role="owner")
    token = A.create_token(owner, "partner")
    user = A.require_role("partner")(authorization=f"Bearer {token}")
    assert user.partner_role == "owner"
