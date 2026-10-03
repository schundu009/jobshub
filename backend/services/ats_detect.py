"""
Which ATS board is behind a careers URL.

detect(careers_url) tries, in order:
  1. the URL itself (boards.greenhouse.io/acme, jobs.lever.co/acme,
     acme.wd5.myworkdayjobs.com/en-US/Careers, ...);
  2. the page's links and scripts (fetched once; an embedded Greenhouse
     board, an "Open roles" link to Lever, ...);
and keeps a candidate only when its public job API answers with jobs.

Only the employer's published job interfaces are read: one page fetch, then
the ATS's own JSON API.
"""

import logging
import re
from typing import Optional
from urllib.parse import parse_qs, urljoin, urlparse

import httpx

from scrapers.board_scraper import SUPPORTED_ATS, api_url

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (compatible; CariaraJobs/1.0; +https://cariara.com)"
TIMEOUT = 15
MAX_REDIRECTS = 3
MAX_CANDIDATES = 4  # API probes per detection when the page links several boards

_TOKEN = re.compile(r"[A-Za-z0-9_.\-]{1,120}")
_WORKDAY_HOST = re.compile(r"([a-z0-9\-]+)\.wd\d+\.myworkdayjobs\.com")
_LOCALE = re.compile(r"[a-z]{2}[-_][A-Za-z]{2}")
# ATS links in a page: href/src values and script strings, absolute or protocol-relative.
_ATS_LINK = re.compile(
    r"(?:https?:)?//(?:[a-z0-9\-]+\.)*(?:greenhouse\.io|lever\.co|ashbyhq\.com|smartrecruiters\.com|myworkdayjobs\.com)"
    r"[^\s\"'<>\\)]*",
    re.IGNORECASE,
)


def _token(value: Optional[str]) -> Optional[str]:
    return value if value and _TOKEN.fullmatch(value) else None


def match_url(url: str) -> Optional[tuple[str, str]]:
    """(ats, board) when the URL itself is on a supported ATS board, else None."""
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    elif "://" not in url:
        url = "https://" + url
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    segs = [s for s in parsed.path.split("/") if s]
    lower = [s.lower() for s in segs]

    if host in ("boards.greenhouse.io", "job-boards.greenhouse.io", "boards-api.greenhouse.io"):
        # Embedded boards: boards.greenhouse.io/embed/job_board?for=acme
        board = (parse_qs(parsed.query).get("for") or [None])[0]
        if not board and lower[:2] == ["v1", "boards"] and len(segs) > 2:
            board = segs[2]
        elif not board and segs and lower[0] not in ("embed", "v1"):
            board = segs[0]
        board = _token(board)
        return ("greenhouse", board.lower()) if board else None

    if host == "jobs.lever.co" and segs:
        board = _token(segs[0])
        return ("lever", board) if board else None
    if host == "api.lever.co" and lower[:2] == ["v0", "postings"] and len(segs) > 2:
        board = _token(segs[2])
        return ("lever", board) if board else None

    if host == "jobs.ashbyhq.com" and segs:
        board = _token(segs[0])
        return ("ashby", board) if board else None
    if host == "api.ashbyhq.com" and lower[:2] == ["posting-api", "job-board"] and len(segs) > 2:
        board = _token(segs[2])
        return ("ashby", board) if board else None

    if host in ("jobs.smartrecruiters.com", "careers.smartrecruiters.com") and segs:
        board = _token(segs[0])
        return ("smartrecruiters", board) if board else None
    if host == "api.smartrecruiters.com" and lower[:2] == ["v1", "companies"] and len(segs) > 2:
        board = _token(segs[2])
        return ("smartrecruiters", board) if board else None

    m = _WORKDAY_HOST.fullmatch(host)
    if m:
        if lower[:2] == ["wday", "cxs"] and len(segs) > 3:
            tenant, site = segs[2], segs[3]
        else:
            rest = segs[1:] if segs and _LOCALE.fullmatch(segs[0]) else segs
            tenant, site = m.group(1), (rest[0] if rest else None)
        if _token(tenant) and _token(site) and site.lower() not in ("job", "wday"):
            return ("workday", f"{host}/{tenant}/{site}")
    return None


def candidates_in_html(html: str, base_url: str = "") -> list[tuple[str, str]]:
    """Every distinct (ats, board) linked from a page, in page order."""
    found: list[tuple[str, str]] = []
    for link in _ATS_LINK.findall(html or ""):
        hit = match_url(urljoin(base_url, link) if base_url else link)
        if hit and hit not in found:
            found.append(hit)
    return found


def _fetch_page(url: str) -> Optional[tuple[str, str]]:
    """(final_url, html) of a careers page, following a few redirects that stay SSRF-safe."""
    from utils.security import validate_url_ssrf_safe

    try:
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False,
                          headers={"User-Agent": USER_AGENT, "Accept": "text/html,*/*"}) as client:
            for _ in range(MAX_REDIRECTS + 1):
                ok, _err = validate_url_ssrf_safe(url)
                if not ok:
                    return None
                resp = client.get(url)
                if resp.is_redirect and resp.headers.get("location"):
                    url = urljoin(url, resp.headers["location"])
                    continue
                if resp.status_code != 200:
                    return None
                return url, resp.text
    except Exception as e:
        logger.info(f"ats_detect: could not fetch {url}: {type(e).__name__}: {e}")
    return None


def probe(ats: str, board: str) -> int:
    """How many jobs the board's public API lists (0 when it answers with none or fails)."""
    url = api_url(ats, board)
    if not url:
        return 0
    try:
        with httpx.Client(timeout=TIMEOUT, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}) as client:
            if ats == "workday":
                resp = client.post(url, json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
            elif ats == "smartrecruiters":
                resp = client.get(url, params={"limit": 1})
            else:
                resp = client.get(url)
            if resp.status_code != 200:
                return 0
            data = resp.json()
    except Exception as e:
        logger.info(f"ats_detect: probe {ats}/{board} failed: {type(e).__name__}: {e}")
        return 0
    return _job_count(ats, data)


def _job_count(ats: str, data) -> int:
    if ats == "lever":
        return len(data) if isinstance(data, list) else 0
    if not isinstance(data, dict):
        return 0
    if ats == "workday":
        return int(data.get("total") or 0) or len(data.get("jobPostings") or [])
    if ats == "smartrecruiters":
        return int(data.get("totalFound") or 0) or len(data.get("content") or [])
    if ats == "ashby":
        return len([j for j in data.get("jobs") or [] if isinstance(j, dict) and j.get("isListed", True)])
    return len(data.get("jobs") or [])


def detect(careers_url: str) -> Optional[dict]:
    """
    {ats, board, api_url, job_count} for the board behind careers_url, or None
    when no supported ATS board with jobs was found.
    """
    hit = match_url(careers_url)
    candidates = [hit] if hit else []
    if not candidates:
        page = _fetch_page(careers_url)
        if page:
            candidates = candidates_in_html(page[1], page[0])
    for ats, board in candidates[:MAX_CANDIDATES]:
        if ats not in SUPPORTED_ATS:
            continue
        count = probe(ats, board)
        if count > 0:
            return {"ats": ats, "board": board, "api_url": api_url(ats, board), "job_count": count}
    return None
