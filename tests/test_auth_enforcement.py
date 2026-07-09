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
