"""
Redis service for caching, session management, and rate limiting.

Provides async-compatible Redis operations for:
- Token blacklist (logout/revocation)
- Distributed rate limiting
- Session storage
- Query caching
"""

import json
import time
from datetime import datetime, timezone
from typing import Optional, Any, List
import redis
from contextlib import contextmanager

try:
    from config import settings
except ImportError:
    from config import settings


class RedisService:
    """
    Redis service for distributed caching and state management.

    Uses connection pooling for efficiency.
    """

    # Key prefixes for namespacing
    PREFIX_TOKEN_BLACKLIST = "blacklist:token:"
    PREFIX_RATE_LIMIT = "ratelimit:"
    PREFIX_SESSION = "session:"
    PREFIX_CACHE = "cache:"

    def __init__(self, redis_url: Optional[str] = None):
        """Initialize Redis connection pool."""
        self.redis_url = redis_url or settings.redis_url
        self._pool = None
        self._client = None

    @property
    def pool(self) -> redis.ConnectionPool:
        """Lazy-initialize connection pool."""
        if self._pool is None:
            self._pool = redis.ConnectionPool.from_url(
                self.redis_url,
                max_connections=10,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
        return self._pool

    @property
    def client(self) -> redis.Redis:
        """Get Redis client from pool."""
        if self._client is None:
            self._client = redis.Redis(connection_pool=self.pool)
        return self._client

    def ping(self) -> bool:
        """Check if Redis is available."""
        try:
            return self.client.ping()
        except Exception:
            return False

    # =========================================================================
    # TOKEN BLACKLIST (for logout/revocation)
    # =========================================================================

    def blacklist_token(self, jti: str, expires_in_seconds: int) -> bool:
        """
        Add a token to the blacklist.

        Args:
            jti: The JWT token ID (jti claim)
            expires_in_seconds: TTL matching token expiry

        Returns:
            True if successful
        """
        key = f"{self.PREFIX_TOKEN_BLACKLIST}{jti}"
        try:
            self.client.setex(key, expires_in_seconds, "1")
            return True
        except redis.RedisError:
            return False

    def is_token_blacklisted(self, jti: str) -> bool:
        """
        Check if a token is blacklisted.

        Args:
            jti: The JWT token ID (jti claim)

        Returns:
            True if blacklisted
        """
        key = f"{self.PREFIX_TOKEN_BLACKLIST}{jti}"
        try:
            return self.client.exists(key) == 1
        except redis.RedisError:
            # Fail open on Redis errors (log this in production)
            return False

    def blacklist_user_tokens(self, user_id: int, expires_in_seconds: int) -> bool:
        """
        Blacklist all tokens for a user (force logout everywhere).

        Uses a user-level marker that invalidates tokens issued before this time.

        Args:
            user_id: The user's ID
            expires_in_seconds: TTL (should be max token lifetime)

        Returns:
            True if successful
        """
        key = f"{self.PREFIX_TOKEN_BLACKLIST}user:{user_id}"
        try:
            # Store timestamp - any token issued before this is invalid
            self.client.setex(key, expires_in_seconds, str(int(time.time())))
            return True
        except redis.RedisError:
            return False

    def get_user_blacklist_time(self, user_id: int) -> Optional[int]:
        """
        Get the blacklist timestamp for a user.

        Returns:
            Unix timestamp or None if not blacklisted
        """
        key = f"{self.PREFIX_TOKEN_BLACKLIST}user:{user_id}"
        try:
            val = self.client.get(key)
            return int(val) if val else None
        except redis.RedisError:
            return None

    # =========================================================================
    # RATE LIMITING (distributed, per-user)
    # =========================================================================

    def check_rate_limit(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        endpoint_category: str = "default"
    ) -> tuple[bool, int, int]:
        """
        Check and update rate limit for an identifier.

        Uses sliding window algorithm with Redis sorted sets.

        Args:
            identifier: Client identifier (user_id, IP, API key)
            limit: Max requests per window
            window_seconds: Time window in seconds
            endpoint_category: Category for different limits (auth, api, scraper)

        Returns:
            Tuple of (is_allowed, remaining_requests, retry_after_seconds)
        """
        key = f"{self.PREFIX_RATE_LIMIT}{endpoint_category}:{identifier}"
        now = time.time()
        window_start = now - window_seconds

        try:
            pipe = self.client.pipeline()

            # Remove old entries outside the window
            pipe.zremrangebyscore(key, 0, window_start)

            # Count current requests in window
            pipe.zcard(key)

            # Add current request
            pipe.zadd(key, {f"{now}": now})

            # Set expiry on the key
            pipe.expire(key, window_seconds)

            results = pipe.execute()
            current_count = results[1]

            if current_count >= limit:
                # Over limit - calculate retry time
                oldest = self.client.zrange(key, 0, 0, withscores=True)
                if oldest:
                    retry_after = int(oldest[0][1] + window_seconds - now) + 1
                else:
                    retry_after = window_seconds
                return False, 0, retry_after

            remaining = limit - current_count - 1
            return True, remaining, 0

        except redis.RedisError:
            # Fail open on Redis errors
            return True, limit, 0

    def get_rate_limit_status(
        self,
        identifier: str,
        limit: int,
        window_seconds: int,
        endpoint_category: str = "default"
    ) -> dict:
        """
        Get current rate limit status without incrementing.

        Returns:
            Dict with limit, remaining, and reset timestamp
        """
        key = f"{self.PREFIX_RATE_LIMIT}{endpoint_category}:{identifier}"
        now = time.time()
        window_start = now - window_seconds

        try:
            # Clean and count
            self.client.zremrangebyscore(key, 0, window_start)
            current_count = self.client.zcard(key)

            return {
                "limit": limit,
                "remaining": max(0, limit - current_count),
                "reset": int(now + window_seconds),
            }
        except redis.RedisError:
            return {"limit": limit, "remaining": limit, "reset": int(now + window_seconds)}

    # =========================================================================
    # SESSION STORAGE
    # =========================================================================

    def store_session(
        self,
        session_id: str,
        user_id: int,
        data: dict,
        expires_in_seconds: int = 86400  # 24 hours default
    ) -> bool:
        """
        Store session data.

        Args:
            session_id: Unique session identifier
            user_id: The user's ID
            data: Session data dict
            expires_in_seconds: Session TTL

        Returns:
            True if successful
        """
        key = f"{self.PREFIX_SESSION}{session_id}"
        try:
            session_data = {
                "user_id": user_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                **data
            }
            self.client.setex(key, expires_in_seconds, json.dumps(session_data))
            return True
        except redis.RedisError:
            return False

    def get_session(self, session_id: str) -> Optional[dict]:
        """
        Retrieve session data.

        Args:
            session_id: Unique session identifier

        Returns:
            Session data dict or None
        """
        key = f"{self.PREFIX_SESSION}{session_id}"
        try:
            data = self.client.get(key)
            return json.loads(data) if data else None
        except (redis.RedisError, json.JSONDecodeError):
            return None

    def delete_session(self, session_id: str) -> bool:
        """Delete a session."""
        key = f"{self.PREFIX_SESSION}{session_id}"
        try:
            self.client.delete(key)
            return True
        except redis.RedisError:
            return False

    def delete_user_sessions(self, user_id: int) -> int:
        """
        Delete all sessions for a user.

        Note: This requires scanning, so it's not atomic.
        For production, consider maintaining a user->sessions index.

        Returns:
            Number of sessions deleted
        """
        pattern = f"{self.PREFIX_SESSION}*"
        deleted = 0
        try:
            for key in self.client.scan_iter(pattern):
                data = self.client.get(key)
                if data:
                    try:
                        session = json.loads(data)
                        if session.get("user_id") == user_id:
                            self.client.delete(key)
                            deleted += 1
                    except json.JSONDecodeError:
                        pass
            return deleted
        except redis.RedisError:
            return deleted

    # =========================================================================
    # CACHING
    # =========================================================================

    def cache_get(self, key: str) -> Optional[Any]:
        """
        Get a cached value.

        Args:
            key: Cache key (will be prefixed)

        Returns:
            Cached value or None
        """
        full_key = f"{self.PREFIX_CACHE}{key}"
        try:
            data = self.client.get(full_key)
            return json.loads(data) if data else None
        except (redis.RedisError, json.JSONDecodeError):
            return None

    def cache_set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> bool:
        """
        Set a cached value.

        Args:
            key: Cache key (will be prefixed)
            value: Value to cache (must be JSON serializable)
            ttl_seconds: Time to live (uses default if None)

        Returns:
            True if successful
        """
        full_key = f"{self.PREFIX_CACHE}{key}"
        ttl = ttl_seconds or settings.cache_ttl_default
        try:
            self.client.setex(full_key, ttl, json.dumps(value))
            return True
        except (redis.RedisError, TypeError):
            return False

    def cache_delete(self, key: str) -> bool:
        """Delete a cached value."""
        full_key = f"{self.PREFIX_CACHE}{key}"
        try:
            self.client.delete(full_key)
            return True
        except redis.RedisError:
            return False

    def cache_delete_pattern(self, pattern: str) -> int:
        """
        Delete all keys matching a pattern.

        Args:
            pattern: Pattern with wildcards (e.g., "user:123:*")

        Returns:
            Number of keys deleted
        """
        full_pattern = f"{self.PREFIX_CACHE}{pattern}"
        deleted = 0
        try:
            for key in self.client.scan_iter(full_pattern):
                self.client.delete(key)
                deleted += 1
            return deleted
        except redis.RedisError:
            return deleted

    # =========================================================================
    # HEALTH & CLEANUP
    # =========================================================================

    def health_check(self) -> dict:
        """
        Get Redis health status.

        Returns:
            Dict with connection status and info
        """
        try:
            info = self.client.info("server")
            return {
                "status": "healthy",
                "redis_version": info.get("redis_version"),
                "connected_clients": self.client.info("clients").get("connected_clients"),
                "used_memory_human": self.client.info("memory").get("used_memory_human"),
            }
        except redis.RedisError as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }

    def close(self):
        """Close Redis connections."""
        if self._client:
            self._client.close()
        if self._pool:
            self._pool.disconnect()


# Global instance
redis_service = RedisService()


# Convenience functions for common operations
def blacklist_token(jti: str, expires_in_seconds: int) -> bool:
    """Blacklist a token by JTI."""
    return redis_service.blacklist_token(jti, expires_in_seconds)


def is_token_blacklisted(jti: str) -> bool:
    """Check if a token is blacklisted."""
    return redis_service.is_token_blacklisted(jti)


def check_rate_limit(
    identifier: str,
    limit: int = 100,
    window_seconds: int = 60,
    endpoint_category: str = "default"
) -> tuple[bool, int, int]:
    """Check rate limit for an identifier."""
    return redis_service.check_rate_limit(identifier, limit, window_seconds, endpoint_category)
