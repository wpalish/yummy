"""Тесты серверной проверки подписи Telegram Login (без реального бота).

Валидную подпись можно вычислить в тесте тем же алгоритмом, что и Telegram —
это проверяет, что verify_telegram_auth принимает корректные данные и
отклоняет подделку/устаревание.
"""
import hashlib
import hmac
import time

import pytest

from app.auth_telegram import verify_telegram_auth

TOKEN = "123456:TEST_BOT_TOKEN"


def _sign(data: dict, token: str) -> str:
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hashlib.sha256(token.encode()).digest()
    return hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()


def _valid_payload() -> dict:
    data = {"id": "42", "first_name": "Алишер", "auth_date": str(int(time.time()))}
    data["hash"] = _sign(data, TOKEN)
    return data


def test_accepts_valid_signature():
    user = verify_telegram_auth(_valid_payload(), TOKEN)
    assert user["id"] == "42"
    assert user["first_name"] == "Алишер"


def test_rejects_forged_hash():
    data = _valid_payload()
    data["hash"] = "deadbeef" * 8
    with pytest.raises(ValueError, match="подпись"):
        verify_telegram_auth(data, TOKEN)


def test_rejects_tampered_field():
    data = _valid_payload()
    data["id"] = "999"  # подменили id после подписи
    with pytest.raises(ValueError, match="подпись"):
        verify_telegram_auth(data, TOKEN)


def test_rejects_wrong_token():
    with pytest.raises(ValueError, match="подпись"):
        verify_telegram_auth(_valid_payload(), "999:OTHER_TOKEN")


def test_rejects_outdated():
    data = {"id": "42", "first_name": "A", "auth_date": str(int(time.time()) - 90000)}
    data["hash"] = _sign(data, TOKEN)
    with pytest.raises(ValueError, match="устарел"):
        verify_telegram_auth(data, TOKEN)


def test_endpoint_501_without_token():
    """Без TELEGRAM_BOT_TOKEN эндпоинт честно отвечает 501, а не падает."""
    pytest.importorskip("httpx")  # TestClient требует httpx (ставится в CI)
    from fastapi.testclient import TestClient

    from app.main import app

    r = TestClient(app).get("/auth/telegram", params={
        "id": 1, "first_name": "A", "auth_date": int(time.time()), "hash": "x"})
    assert r.status_code == 501
