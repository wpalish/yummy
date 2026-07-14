"""Distributed Redis limiter: atomic budgets, pseudonymous keys and fail-closed."""
from __future__ import annotations

import pytest
from redis.exceptions import ConnectionError

from app.distributed_limit import DistributedLimiter


class FakeRedis:
    def __init__(self, replies=None, error=None):
        self.replies = list(replies or [])
        self.error = error
        self.keys = []

    def eval(self, script, number_of_keys, key, window):
        assert "INCR" in script and "EXPIRE" in script
        assert number_of_keys == 1 and int(window) > 0
        self.keys.append(key)
        if self.error:
            raise self.error
        return self.replies.pop(0)


def test_unconfigured_limiter_is_noop():
    limiter = DistributedLimiter("")
    assert limiter.check("auth", "127.0.0.1", 1, 60) == (True, 0)


def test_redis_budget_and_keys_do_not_contain_raw_identity():
    limiter = DistributedLimiter("")
    limiter.client = FakeRedis(replies=[(1, 60), (3, 42)])
    allowed = limiter.check("auth", "203.0.113.77", 2, 60)
    denied = limiter.check("auth", "203.0.113.77", 2, 60)
    assert allowed == (True, 60) and denied == (False, 42)
    assert all("203.0.113.77" not in key and key.startswith("yummy:rl:auth:")
               for key in limiter.client.keys)


def test_configured_redis_failure_is_not_silently_bypassed():
    limiter = DistributedLimiter("")
    limiter.client = FakeRedis(error=ConnectionError("down"))
    with pytest.raises(RuntimeError, match="unavailable"):
        limiter.check("orders", "ip", 10, 60)


def test_http_middleware_returns_429_and_retry_after(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as main_mod

    monkeypatch.setattr(main_mod.distributed_limiter, "configured", True)
    monkeypatch.setattr(main_mod.distributed_limiter, "check",
                        lambda bucket, identity, limit, window: (False, 17))
    response = TestClient(main_mod.app).get("/health")
    assert response.status_code == 429
    assert response.headers["retry-after"] == "17"
