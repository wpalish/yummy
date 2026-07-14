"""Deny-by-default и ролевая защита private API."""
import pytest
from fastapi import HTTPException

import app.accounts as A


def _request(cookies: str = ""):
    from starlette.requests import Request

    headers = [(b"cookie", cookies.encode())] if cookies else []
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_privileged_access_always_requires_token():
    dep = A.require_role("admin")
    with pytest.raises(HTTPException) as exc:
        dep(request=_request(), authorization=None)
    assert exc.value.status_code == 401


def test_role_mismatch_403(tmp_path, monkeypatch):
    acc = A.Accounts(path=tmp_path / "e.db")
    monkeypatch.setattr(A, "accounts", acc)
    uid = acc.create("u@x.kz", A.hash_password("Secret123"), "customer")
    token = A.create_token(uid, "customer")

    with pytest.raises(HTTPException) as exc:
        A.require_role("admin")(request=_request(), authorization=f"Bearer {token}")
    assert exc.value.status_code == 403

    user = A.require_role("customer", "admin")(
        request=_request(), authorization=f"Bearer {token}"
    )
    assert user.role == "customer"


def test_disabled_account_rejected_even_with_unexpired_token(tmp_path, monkeypatch):
    acc = A.Accounts(path=tmp_path / "disabled.db")
    monkeypatch.setattr(A, "accounts", acc)
    uid = acc.create("disabled@x.kz", A.hash_password("Secret123"), "customer")
    token = A.create_token(uid, "customer")
    with acc._conn() as conn:
        conn.execute("UPDATE users SET is_active=0 WHERE id=?", (uid,))

    with pytest.raises(HTTPException) as exc:
        A.current_user(request=_request(), authorization=f"Bearer {token}")
    assert exc.value.status_code == 401
