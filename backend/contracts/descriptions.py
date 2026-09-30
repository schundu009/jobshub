"""
Descriptions on demand for staffing sources whose list API carries none.

GET /api/contracts/jobs/{id} calls ``describe(db, job)``: a stored description is
returned as-is ("stored"); otherwise, for a source in DESCRIPTION_SOURCES, the
public posting page (job_url) is fetched once - plain GET, polite UA, robots.txt
respected for that path, hard deadline - the per-source extractor
``contracts.scrapers.<module>.fetch_description(url) -> (html, text)`` pulls
the description, it is stored on the row and returned ("fetched"). Any failure
-> "unavailable" (and a short negative cache so a dead page is not re-hit on
every view).

Extractors use ``polite_get`` below for their HTTP so all of them share the
robots / timeout / UA rules. Never scrape behind logins or CAPTCHAs: an
extractor returns (None, None) when the page is not the public posting.
"""
from __future__ import annotations

import concurrent.futures
import importlib
import logging
import re
import time
from typing import Callable, Optional
from urllib import robotparser
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; CariaraJobsBot/1.0; +https://jobs.cariara.com)"
FETCH_TIMEOUT = 10.0  # per HTTP request
DEADLINE = 12.0  # whole on-demand fetch, including robots.txt
MAX_BYTES = 3_000_000
FAILED_TTL = 6 * 3600  # don't retry a failed page for 6 hours (per process)

# source slug -> module in contracts.scrapers that defines fetch_description(url)
DESCRIPTION_SOURCES: dict[str, str] = {
    "collabera": "collabera",
    "insightglobal": "insightglobal",
    "akkodis": "akkodis",
    "motionrecruitment": "motion",
}

_robots_cache: dict[str, tuple[float, Optional[robotparser.RobotFileParser]]] = {}
_failed: dict[int, float] = {}
_ROBOTS_TTL = 6 * 3600


class FetchBlocked(Exception):
    """robots.txt disallows the path (or the page is not a public posting)."""


def _robots(url: str, timeout: float) -> Optional[robotparser.RobotFileParser]:
    import httpx
    p = urlparse(url)
    base = f"{p.scheme}://{p.netloc}"
    cached = _robots_cache.get(base)
    if cached and time.time() - cached[0] < _ROBOTS_TTL:
        return cached[1]
    rp: Optional[robotparser.RobotFileParser] = robotparser.RobotFileParser()
    try:
        r = httpx.get(base + "/robots.txt", timeout=timeout, headers={"User-Agent": USER_AGENT},
                      follow_redirects=True)
        if r.status_code in (401, 403):
            rp.parse(["User-agent: *", "Disallow: /"])
        elif r.status_code >= 400:
            rp = None  # no robots.txt: everything allowed
        else:
            rp.parse(r.text.splitlines())
    except Exception:
        rp = None  # unreachable robots.txt: treat as allowed (the page GET will fail anyway)
    _robots_cache[base] = (time.time(), rp)
    return rp


def robots_allowed(url: str, timeout: float = FETCH_TIMEOUT) -> bool:
    rp = _robots(url, timeout)
    return True if rp is None else rp.can_fetch(USER_AGENT, url)


def polite_get(url: str, timeout: float = FETCH_TIMEOUT, **kwargs):
    """GET a public page: robots.txt checked, polite UA, timeout, size cap. Returns an httpx.Response."""
    import httpx
    if not re.match(r"^https?://", url or "", re.I):
        raise FetchBlocked("not an http(s) url")
    if not robots_allowed(url, timeout):
        raise FetchBlocked(f"robots.txt disallows {url}")
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html,application/json;q=0.9,*/*;q=0.8"}
    headers.update(kwargs.pop("headers", {}) or {})
    r = httpx.get(url, timeout=timeout, headers=headers, follow_redirects=True, **kwargs)
    r.raise_for_status()
    if len(r.content) > MAX_BYTES:
        raise FetchBlocked("page too large")
    return r


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\r\f\v]+")


def html_to_text(fragment: Optional[str]) -> Optional[str]:
    """Description HTML -> readable text (block tags become line breaks)."""
    if not fragment:
        return None
    import html as _html
    s = re.sub(r"(?i)<\s*(br|/p|/div|/li|/h[1-6]|/tr)\s*/?>", "\n", fragment)
    s = re.sub(r"(?i)<\s*li[^>]*>", "\n- ", s)
    s = _html.unescape(_TAG_RE.sub(" ", s))
    lines = [_WS_RE.sub(" ", ln).strip() for ln in s.splitlines()]
    text = "\n".join(ln for ln in lines if ln)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text or None


def _fetcher(source: Optional[str]) -> Optional[Callable[[str], tuple]]:
    module = DESCRIPTION_SOURCES.get(source or "")
    if not module:
        return None
    try:
        mod = importlib.import_module(f"contracts.scrapers.{module}")
    except Exception as e:  # pragma: no cover
        logger.warning(f"description extractor {module} failed to import: {e}")
        return None
    return getattr(mod, "fetch_description", None)


_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="contract-desc")


def fetch_with_deadline(source: str, url: str, deadline: float = DEADLINE) -> tuple[Optional[str], Optional[str]]:
    """(html, text) or (None, None); never blocks longer than ``deadline`` seconds."""
    fn = _fetcher(source)
    if fn is None or not url:
        return None, None
    future = _pool.submit(fn, url)
    try:
        out = future.result(timeout=deadline)
    except concurrent.futures.TimeoutError:
        logger.info(f"description fetch timed out for {source}: {url}")
        return None, None
    except FetchBlocked as e:
        logger.info(f"description fetch blocked for {source}: {e}")
        return None, None
    except Exception as e:
        logger.info(f"description fetch failed for {source}: {type(e).__name__}: {e}")
        return None, None
    if not out or not isinstance(out, tuple):
        return None, None
    html, text = (out + (None, None))[:2]
    if not (text or "").strip() and not (html or "").strip():
        return None, None
    return html, text or html_to_text(html)


def describe(db, job, fetch: bool = True) -> str:
    """
    Make sure ``job.description`` is filled when possible; returns the
    description_status: "stored" | "fetched" | "unavailable".
    """
    if (job.description or "").strip():
        return "stored"
    if not fetch or job.source not in DESCRIPTION_SOURCES or not job.job_url:
        return "unavailable"
    failed_at = _failed.get(job.id)
    if failed_at and time.time() - failed_at < FAILED_TTL:
        return "unavailable"
    html, text = fetch_with_deadline(job.source, job.job_url)
    body = html or text
    if not body:
        _failed[job.id] = time.time()
        return "unavailable"
    job.description = body
    try:
        # Skills from the description help profile matching; keep the listed ones.
        from contracts.service import extract_skills
        skills = extract_skills(job.title, text or html_to_text(html) or "", job.skills or [])
        if skills:
            job.skills = skills
        db.commit()
    except Exception as e:
        logger.warning(f"storing fetched description for contract job {job.id} failed: {e}")
        try:
            db.rollback()
        except Exception:
            pass
    return "fetched"
