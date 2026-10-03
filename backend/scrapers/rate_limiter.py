"""
Rate Limiter - rate limiting for scrapers.

- RateLimiter / AdaptiveRateLimiter: per-slug sliding window, one acquire
  per scrape run (in-process).
- HostRateLimiter: per-host token bucket around every request, shared by
  all workers through Redis, so the ~250 scrapers that hit one host
  (boards-api.greenhouse.io, api.lever.co, ...) stay polite together. When
  Redis can't be reached it limits in-process instead.
"""

import asyncio
import os
import time
from collections import defaultdict
from email.utils import parsedate_to_datetime
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Per-domain rate limiter using sliding window algorithm.

    Usage:
        limiter = RateLimiter(default_rate=30)  # 30 requests/minute
        limiter.set_rate("google", 20)  # Custom rate for Google

        await limiter.acquire("microsoft")  # Will wait if rate exceeded
    """

    def __init__(
        self,
        default_rate: int = 30,
        window_seconds: int = 60,
    ):
        """
        Initialize the rate limiter.

        Args:
            default_rate: Default requests per window
            window_seconds: Size of the sliding window in seconds
        """
        self.default_rate = default_rate
        self.window_seconds = window_seconds

        # Per-domain rate limits
        self._rates: dict[str, int] = {}

        # Sliding window tracking: domain -> list of timestamps
        self._windows: dict[str, list[float]] = defaultdict(list)

        # Lock for thread safety
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def set_rate(self, domain: str, rate: int):
        """
        Set a custom rate limit for a domain.

        Args:
            domain: Domain or company slug
            rate: Requests per window
        """
        self._rates[domain] = rate
        logger.debug(f"Set rate limit for {domain}: {rate} req/{self.window_seconds}s")

    def get_rate(self, domain: str) -> int:
        """
        Get the rate limit for a domain.

        Args:
            domain: Domain or company slug

        Returns:
            Rate limit (requests per window)
        """
        return self._rates.get(domain, self.default_rate)

    async def acquire(self, domain: str) -> float:
        """
        Acquire permission to make a request.

        Blocks until a request slot is available within the rate limit.

        Args:
            domain: Domain or company slug

        Returns:
            Wait time in seconds (0 if no wait needed)
        """
        async with self._locks[domain]:
            rate = self.get_rate(domain)
            now = time.time()
            window_start = now - self.window_seconds

            # Remove timestamps outside the window
            self._windows[domain] = [
                ts for ts in self._windows[domain]
                if ts > window_start
            ]

            # Check if we're at the rate limit
            if len(self._windows[domain]) >= rate:
                # Calculate wait time until oldest request expires
                oldest = self._windows[domain][0]
                wait_time = oldest - window_start

                if wait_time > 0:
                    logger.debug(
                        f"Rate limited on {domain}, waiting {wait_time:.2f}s "
                        f"({len(self._windows[domain])}/{rate} requests)"
                    )
                    await asyncio.sleep(wait_time)

                    # Clean up after waiting
                    now = time.time()
                    window_start = now - self.window_seconds
                    self._windows[domain] = [
                        ts for ts in self._windows[domain]
                        if ts > window_start
                    ]
                else:
                    wait_time = 0
            else:
                wait_time = 0

            # Record this request
            self._windows[domain].append(time.time())

            return wait_time

    def try_acquire(self, domain: str) -> bool:
        """
        Try to acquire a request slot without blocking.

        Args:
            domain: Domain or company slug

        Returns:
            True if acquired, False if rate limited
        """
        rate = self.get_rate(domain)
        now = time.time()
        window_start = now - self.window_seconds

        # Remove timestamps outside the window
        self._windows[domain] = [
            ts for ts in self._windows[domain]
            if ts > window_start
        ]

        # Check if we have capacity
        if len(self._windows[domain]) < rate:
            self._windows[domain].append(now)
            return True

        return False

    def get_remaining(self, domain: str) -> int:
        """
        Get remaining requests in the current window.

        Args:
            domain: Domain or company slug

        Returns:
            Number of remaining requests
        """
        rate = self.get_rate(domain)
        now = time.time()
        window_start = now - self.window_seconds

        # Count requests in window
        current = len([
            ts for ts in self._windows[domain]
            if ts > window_start
        ])

        return max(0, rate - current)

    def get_reset_time(self, domain: str) -> Optional[float]:
        """
        Get seconds until the rate limit resets.

        Args:
            domain: Domain or company slug

        Returns:
            Seconds until reset, or None if not rate limited
        """
        rate = self.get_rate(domain)
        now = time.time()
        window_start = now - self.window_seconds

        # Get active timestamps
        active = [ts for ts in self._windows[domain] if ts > window_start]

        if len(active) >= rate and active:
            oldest = min(active)
            return (oldest + self.window_seconds) - now

        return None

    def clear(self, domain: Optional[str] = None):
        """
        Clear rate limit tracking.

        Args:
            domain: Optional domain to clear, or None for all
        """
        if domain:
            self._windows[domain].clear()
        else:
            self._windows.clear()

    def stats(self) -> dict:
        """
        Get rate limiter statistics.

        Returns:
            Dict with per-domain stats
        """
        now = time.time()
        window_start = now - self.window_seconds

        stats = {}
        for domain in set(list(self._windows.keys()) + list(self._rates.keys())):
            rate = self.get_rate(domain)
            current = len([
                ts for ts in self._windows.get(domain, [])
                if ts > window_start
            ])
            stats[domain] = {
                "rate_limit": rate,
                "current_requests": current,
                "remaining": max(0, rate - current),
                "window_seconds": self.window_seconds,
            }

        return stats


class AdaptiveRateLimiter(RateLimiter):
    """
    Rate limiter that adapts based on response patterns.

    Automatically reduces rate on 429 responses and gradually
    increases when successful.
    """

    def __init__(
        self,
        default_rate: int = 30,
        window_seconds: int = 60,
        min_rate: int = 5,
        backoff_factor: float = 0.5,
        recovery_factor: float = 1.1,
        recovery_threshold: int = 10,
    ):
        """
        Initialize the adaptive rate limiter.

        Args:
            default_rate: Default requests per window
            window_seconds: Size of the sliding window
            min_rate: Minimum rate limit
            backoff_factor: Multiply rate by this on 429
            recovery_factor: Multiply rate by this on recovery
            recovery_threshold: Successful requests before recovery
        """
        super().__init__(default_rate, window_seconds)
        self.min_rate = min_rate
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        self.recovery_threshold = recovery_threshold

        # Track consecutive successes
        self._success_counts: dict[str, int] = defaultdict(int)
        # Track original rates
        self._original_rates: dict[str, int] = {}

    def record_success(self, domain: str):
        """
        Record a successful request.

        Args:
            domain: Domain or company slug
        """
        self._success_counts[domain] += 1

        # Check if we should recover
        if self._success_counts[domain] >= self.recovery_threshold:
            current_rate = self.get_rate(domain)
            original_rate = self._original_rates.get(
                domain,
                self._rates.get(domain, self.default_rate)
            )

            if current_rate < original_rate:
                new_rate = min(
                    int(current_rate * self.recovery_factor),
                    original_rate
                )
                self._rates[domain] = new_rate
                logger.info(
                    f"Recovering rate limit for {domain}: {current_rate} -> {new_rate}"
                )

            self._success_counts[domain] = 0

    def record_rate_limited(self, domain: str):
        """
        Record a rate-limited response (429).

        Args:
            domain: Domain or company slug
        """
        current_rate = self.get_rate(domain)

        # Save original rate if not saved
        if domain not in self._original_rates:
            self._original_rates[domain] = current_rate

        new_rate = max(
            int(current_rate * self.backoff_factor),
            self.min_rate
        )

        self._rates[domain] = new_rate
        self._success_counts[domain] = 0

        logger.warning(
            f"Backing off rate limit for {domain}: {current_rate} -> {new_rate}"
        )

    def reset_to_original(self, domain: str):
        """
        Reset a domain's rate limit to its original value.

        Args:
            domain: Domain or company slug
        """
        if domain in self._original_rates:
            self._rates[domain] = self._original_rates[domain]
            del self._original_rates[domain]
            self._success_counts[domain] = 0
            logger.info(f"Reset rate limit for {domain} to original")


# Global rate limiter instance
_global_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """
    Get the global rate limiter instance.

    Returns:
        Global RateLimiter instance
    """
    global _global_limiter
    if _global_limiter is None:
        _global_limiter = AdaptiveRateLimiter()
    return _global_limiter


def set_rate_limiter(limiter: RateLimiter):
    """
    Set the global rate limiter instance.

    Args:
        limiter: RateLimiter instance to use
    """
    global _global_limiter
    _global_limiter = limiter


# ---------------------------------------------------------------- per-host bucket

# Requests per minute per host, and how many may go back to back.
HOST_RATE_PER_MINUTE = int(os.environ.get("SCRAPER_HOST_RATE_PER_MINUTE", "120"))
HOST_BURST = int(os.environ.get("SCRAPER_HOST_BURST", "10"))

# Token bucket in one round trip: refill by elapsed time, take a token or
# return how long until one is due. Returned as a string (Lua numbers come
# back from Redis as integers).
_BUCKET_LUA = """
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local data = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(data[1]) or burst
local ts = tonumber(data[2]) or now
tokens = math.min(burst, tokens + math.max(0, now - ts) * rate)
local wait = 0
if tokens >= 1 then tokens = tokens - 1 else wait = (1 - tokens) / rate end
redis.call('HSET', KEYS[1], 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', KEYS[1], math.ceil(burst / rate) + 60)
return tostring(wait)
"""


def _redis_client():
    """The shared Redis client, or None while it is unreachable (circuit open)."""
    try:
        from services.redis_service import redis_service
        return redis_service.client if redis_service.available else None
    except Exception:
        return None


class HostRateLimiter:
    """
    Per-host token bucket: rate_per_minute requests, bursts of up to `burst`.

    The bucket lives in Redis (key scrape:host:<host>) so every worker draws
    from the same one; if Redis fails the call is answered by an in-process
    bucket, which still keeps one worker polite.
    """

    KEY_PREFIX = "scrape:host:"

    def __init__(
        self,
        rate_per_minute: int = HOST_RATE_PER_MINUTE,
        burst: int = HOST_BURST,
        redis_factory: Callable = _redis_client,
    ):
        self.rate = max(rate_per_minute, 1) / 60.0  # tokens per second
        self.burst = max(burst, 1)
        self._redis_factory = redis_factory
        self._script = None
        self._local: dict[str, tuple[float, float]] = {}  # host -> (tokens, ts)

    def _take_redis(self, host: str) -> Optional[float]:
        client = self._redis_factory()
        if client is None:
            return None
        try:
            if self._script is None:
                self._script = client.register_script(_BUCKET_LUA)
            return float(self._script(keys=[self.KEY_PREFIX + host], args=[self.rate, self.burst, time.time()]))
        except Exception as e:
            logger.debug(f"host bucket in Redis unavailable ({type(e).__name__}); limiting in-process")
            self._script = None
            return None

    def _take_local(self, host: str) -> float:
        now = time.monotonic()
        tokens, ts = self._local.get(host, (float(self.burst), now))
        tokens = min(self.burst, tokens + max(0.0, now - ts) * self.rate)
        if tokens >= 1:
            self._local[host] = (tokens - 1, now)
            return 0.0
        self._local[host] = (tokens, now)
        return (1 - tokens) / self.rate

    def take(self, host: str) -> float:
        """Take a token for host: 0 when granted, else seconds until one is due."""
        if not host:
            return 0.0
        wait = self._take_redis(host)
        return self._take_local(host) if wait is None else wait

    async def acquire(self, host: str) -> float:
        """Wait until host may be requested. Returns the time waited."""
        waited = 0.0
        while (wait := self.take(host)) > 0:
            await asyncio.sleep(wait)
            waited += wait
        return waited

    def acquire_sync(self, host: str) -> float:
        """acquire() for blocking code (the description extractor)."""
        waited = 0.0
        while (wait := self.take(host)) > 0:
            time.sleep(wait)
            waited += wait
        return waited


_host_limiter: Optional[HostRateLimiter] = None


def get_host_limiter() -> HostRateLimiter:
    """The process-wide HostRateLimiter."""
    global _host_limiter
    if _host_limiter is None:
        _host_limiter = HostRateLimiter()
    return _host_limiter


def set_host_limiter(limiter: Optional[HostRateLimiter]):
    global _host_limiter
    _host_limiter = limiter


def retry_after_seconds(value: Optional[str]) -> Optional[float]:
    """A Retry-After header (seconds or an HTTP date) in seconds from now; None if absent/invalid."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
        return max(0.0, when.timestamp() - time.time())
    except Exception:
        return None
