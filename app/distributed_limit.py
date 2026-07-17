"""Redis-backed fixed-window limiter for horizontal deployments.

Existing endpoint-local limits remain defense-in-depth. Redis keys contain only a
keyed digest of identity, never raw IP/user data.
"""
from __future__ import annotations

import hashlib
import hmac
import os

from redis import Redis
from redis.exceptions import RedisError

_REDIS_URL = os.getenv("REDIS_URL", "").strip()
_PRODUCTION = os.getenv("YUMMY_ENV", "").lower() == "production"
_KEY_SECRET = os.getenv("YUMMY_RATE_LIMIT_KEY") or os.getenv("YUMMY_DATA_KEY") or "dev-rate-key"

# Atomic increment + first-hit expiry. TTL is returned for Retry-After.
_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
local ttl = redis.call('TTL', KEYS[1])
return {current, ttl}
"""


class DistributedLimiter:
    def __init__(self, url: str = _REDIS_URL, *, production: bool = _PRODUCTION) -> None:
        self.configured = bool(url)
        self.production = production
        self.client = Redis.from_url(
            url, socket_connect_timeout=1.0, socket_timeout=1.0,
            decode_responses=False,
        ) if url else None

    @staticmethod
    def _digest(identity: str) -> str:
        return hmac.new(_KEY_SECRET.encode(), identity.encode(), hashlib.sha256).hexdigest()[:32]

    def worker_healthy(self) -> bool:
        if not self.client:
            return False
        try:
            return bool(self.client.exists("yummy:worker:heartbeat"))
        except RedisError:
            return False

    def check(self, bucket: str, identity: str, limit: int, window: int) -> tuple[bool, int]:
        """Return ``(allowed, retry_after)``; configured Redis errors fail closed."""
        if not self.client:
            return True, 0
        key = f"yummy:rl:{bucket}:{self._digest(identity)}"
        try:
            current, ttl = self.client.eval(_SCRIPT, 1, key, window)
        except RedisError as exc:
            from .observability import record_redis_failure
            record_redis_failure()
            # A configured distributed guard must not silently degrade, otherwise
            # an attacker can trigger failover and bypass limits on every replica.
            raise RuntimeError("distributed rate limiter unavailable") from exc
        ttl = max(int(ttl), 1)
        return int(current) <= limit, ttl


limiter = DistributedLimiter()
