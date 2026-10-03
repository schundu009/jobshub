"""Polite fetching: the shared per-host bucket, Retry-After, and robots.txt for career pages."""
import asyncio
from email.utils import formatdate
import time

import pytest

from scrapers import rate_limiter
from scrapers.base import HTTPScraper, ScraperConfig, ScraperErrorType, ScraperType, ThrottledError
from scrapers.rate_limiter import HostRateLimiter, retry_after_seconds
from services import ingestion_service, robots


# ------------------------------------------------------------------ host bucket

def test_local_bucket_allows_a_burst_then_spaces_requests():
    limiter = HostRateLimiter(rate_per_minute=60, burst=2, redis_factory=lambda: None)
    assert limiter.take("a.example") == 0 and limiter.take("a.example") == 0
    wait = limiter.take("a.example")
    assert 0.9 < wait <= 1.0
    assert limiter.take("b.example") == 0  # per host


class FakeRedis:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, []

    def register_script(self, source):
        assert "HMGET" in source

        def script(keys, args):
            self.calls.append((keys, args))
            if self.error:
                raise self.error
            return self.reply
        return script


def test_bucket_is_shared_through_redis():
    fake = FakeRedis(reply="0.25")
    limiter = HostRateLimiter(rate_per_minute=120, burst=10, redis_factory=lambda: fake)
    assert limiter.take("boards-api.greenhouse.io") == 0.25
    (keys, args), = fake.calls
    assert keys == ["scrape:host:boards-api.greenhouse.io"] and args[:2] == [2.0, 10]


def test_bucket_falls_back_in_process_when_redis_fails():
    fake = FakeRedis(error=ConnectionError("down"))
    limiter = HostRateLimiter(rate_per_minute=60, burst=1, redis_factory=lambda: fake)
    assert limiter.take("x.example") == 0
    assert limiter.take("x.example") > 0  # the local bucket kept count


def test_retry_after_parsing():
    assert retry_after_seconds("7") == 7
    assert 50 < retry_after_seconds(formatdate(time.time() + 60, usegmt=True)) <= 60
    assert retry_after_seconds("soon") is None and retry_after_seconds(None) is None


# ------------------------------------------------------------------ Retry-After

class FakeResponse:
    def __init__(self, status, headers=None, body=None):
        self.status, self.headers, self.body = status, headers or {}, body

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def raise_for_status(self):
        if self.status >= 400:
            import aiohttp
            raise aiohttp.ClientResponseError(None, (), status=self.status, message="err")

    async def json(self):
        return self.body


class FakeSession:
    closed = False

    def __init__(self, responses):
        self.responses, self.requests = list(responses), []

    def request(self, method, url, **kwargs):
        self.requests.append((method, url))
        return self.responses.pop(0)

    async def close(self):
        pass


class Board(HTTPScraper):
    config = ScraperConfig(company_slug="politeco", company_name="Polite Co", careers_url="https://x",
                           scraper_type=ScraperType.HTTP, retry_delay=0)
    API_URL = "https://api.example.com/jobs"
    scrapes = 0

    async def scrape(self):
        type(self).scrapes += 1
        from scrapers.base import ScrapeResult
        data = await self.fetch_json(self.API_URL)
        return ScrapeResult(success=True, jobs=[], jobs_found=len(data["jobs"]))

    def parse_job(self, raw):
        return None


def _scraper(responses):
    scraper = Board()
    scraper._session = FakeSession(responses)
    return scraper


@pytest.fixture(autouse=True)
def _no_sleep(monkeypatch):
    slept = []

    async def sleep(seconds):
        slept.append(seconds)
    monkeypatch.setattr(asyncio, "sleep", sleep)
    return slept


def test_short_retry_after_is_waited_out(_no_sleep):
    scraper = _scraper([FakeResponse(429, {"Retry-After": "3"}), FakeResponse(200, body={"jobs": [1]})])
    assert asyncio.run(scraper.fetch_json(Board.API_URL)) == {"jobs": [1]}
    assert _no_sleep == [3.0] and len(scraper._session.requests) == 2


def test_long_retry_after_gives_up_the_run():
    Board.scrapes = 0
    scraper = _scraper([FakeResponse(503, {"Retry-After": "600"})])
    with pytest.raises(ThrottledError):
        asyncio.run(scraper.fetch_json(Board.API_URL))

    scraper = _scraper([FakeResponse(429, {"Retry-After": "600"})])
    result = asyncio.run(scraper.run())
    assert not result.success and result.error_type == ScraperErrorType.RATE_LIMITED
    assert Board.scrapes == 1  # no retry of the whole scrape


def test_still_throttled_after_waiting_gives_up():
    responses = [FakeResponse(429, {"Retry-After": "1"}) for _ in range(3)]
    scraper = _scraper(responses)
    with pytest.raises(ThrottledError):
        asyncio.run(scraper.fetch_json(Board.API_URL))
    assert len(scraper._session.requests) == 3


def test_429_without_retry_after_is_an_ordinary_http_error():
    import aiohttp
    scraper = _scraper([FakeResponse(429)])
    with pytest.raises(aiohttp.ClientResponseError):
        asyncio.run(scraper.fetch_json(Board.API_URL))


def test_requests_go_through_the_host_bucket(monkeypatch):
    hosts = []

    class Recording(HostRateLimiter):
        async def acquire(self, host):
            hosts.append(host)
            return 0.0
    monkeypatch.setattr(rate_limiter, "_host_limiter", Recording(redis_factory=lambda: None))
    asyncio.run(_scraper([FakeResponse(200, body={"jobs": []})]).fetch_json("https://API.Example.com/x"))
    assert hosts == ["api.example.com"]


# ------------------------------------------------------------------ robots.txt

@pytest.fixture
def robots_txt(monkeypatch):
    robots.clear_cache()
    fetched = []
    answer = {"value": (200, "User-agent: *\nDisallow: /private\n\nUser-agent: CariaraJobs\nDisallow: /nocariara\n")}

    def fetch(url):
        fetched.append(url)
        return answer["value"]
    monkeypatch.setattr(robots, "_fetch_robots", fetch)
    yield answer, fetched
    robots.clear_cache()


def test_robots_rules_are_honoured_and_cached(robots_txt):
    answer, fetched = robots_txt
    assert robots.allowed("https://careers.acme.com/jobs/1")
    assert not robots.allowed("https://careers.acme.com/nocariara/1")
    assert robots.allowed("https://careers.acme.com/private/1")  # our own group replaces '*'
    assert fetched == ["https://careers.acme.com/robots.txt"]


@pytest.mark.parametrize("status,ok", [(404, True), (403, True), (500, False), (None, False)])
def test_robots_missing_or_unreachable(robots_txt, status, ok):
    answer, _ = robots_txt
    answer["value"] = (status, "")
    assert robots.allowed("https://careers.acme.com/jobs/1") is ok


def test_extractor_skips_pages_robots_disallows(robots_txt, monkeypatch):
    answer, _ = robots_txt
    answer["value"] = (200, "User-agent: *\nDisallow: /\n")

    def no_fetch(*a, **k):
        raise AssertionError("page fetched despite robots.txt")
    monkeypatch.setattr(ingestion_service.urllib.request, "urlopen", no_fetch)
    assert ingestion_service.fetch_job_description_from_url("https://careers.acme.com/jobs/1") == ""


def test_extractor_reads_allowed_pages(robots_txt, monkeypatch):
    page = ("<html><script type='application/ld+json'>{\"@type\": \"JobPosting\", \"description\": \""
            + "Build reliable systems. " * 10 + "\"}</script></html>")

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return page.encode()
    monkeypatch.setattr(ingestion_service.urllib.request, "urlopen", lambda *a, **k: Resp())
    assert "Build reliable systems." in ingestion_service.fetch_job_description_from_url("https://careers.acme.com/jobs/1")
