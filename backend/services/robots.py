"""
robots.txt for HTML career pages read by the generic description extractor
(ingestion_service.fetch_job_description_from_url). ATS JSON APIs are the
employers' published job interfaces and are not checked here.

Each site's robots.txt is fetched at most once a day per process. Following
RFC 9309: a 4xx means no rules (allowed); a 5xx or no answer means
"assume disallowed", re-tried after an hour.
"""

import logging
import ssl
import time
import urllib.error
import urllib.request
import urllib.robotparser
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

ROBOTS_AGENT = "CariaraJobs"  # the product token our rules are matched against
USER_AGENT = "Mozilla/5.0 (compatible; CariaraJobs/1.0; +https://cariara.com)"
CACHE_SECONDS = 24 * 3600
UNREACHABLE_CACHE_SECONDS = 3600

_cache: dict[str, tuple[float, urllib.robotparser.RobotFileParser]] = {}


def _ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(certifi.where())
    except ImportError:
        pass
    return ctx


def _fetch_robots(robots_url: str) -> tuple[Optional[int], str]:
    """(status, body) of robots.txt; status None when the site didn't answer."""
    request = urllib.request.Request(robots_url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=10, context=_ssl_context()) as response:
            return response.status, response.read(512 * 1024).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:
        logger.info(f"robots.txt {robots_url} unreachable: {type(e).__name__}: {e}")
        return None, ""


def _parser(origin: str) -> urllib.robotparser.RobotFileParser:
    cached = _cache.get(origin)
    if cached and cached[0] > time.time():
        return cached[1]
    status, body = _fetch_robots(f"{origin}/robots.txt")
    parser = urllib.robotparser.RobotFileParser()
    ttl = CACHE_SECONDS
    if status is not None and 200 <= status < 300:
        parser.parse(body.splitlines())
    elif status is not None and 400 <= status < 500:
        parser.allow_all = True
    else:
        parser.disallow_all = True
        ttl = UNREACHABLE_CACHE_SECONDS
    _cache[origin] = (time.time() + ttl, parser)
    return parser


def allowed(url: str) -> bool:
    """May the extractor fetch this page under the site's robots.txt?"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return False
    return _parser(f"{parsed.scheme}://{parsed.netloc}").can_fetch(ROBOTS_AGENT, url)


def clear_cache() -> None:
    _cache.clear()
