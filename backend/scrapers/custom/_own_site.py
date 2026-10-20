"""
Shared plumbing for companies that list jobs on their OWN website (no hosted ATS).

Every scraper here reads only the public interface the company's careers page
itself uses: its JSON/XHR endpoint, RSS feed, or the server-rendered HTML.

- ``OwnSiteScraper`` (an HTTPScraper) adds a time budget, a cap on postings
  (MAX_JOBS), one network entry point (``_http``, replaced in offline tests),
  robots.txt for HTML pages (services.robots, cached a day) and a ScrapeResult
  that is ``complete`` only when the whole board was read.
- Subclasses implement ``fetch_raw()`` (collect raw postings) and
  ``parse_job()``; most also expose ``listing_items(payload)``, the pure step
  from one listing response to its raw postings, which the tests drive.
- Helpers: ``jsonld_postings`` (schema.org JobPosting blocks in a page),
  ``soup``/``text_of``/``abs_url`` for HTML, and ``JibeMixin`` for careers sites
  on iCIMS Jibe (``/api/jobs``), e.g. careers.amd.com, www.github.careers.

The module name starts with "_" so ScraperRegistry does not import it as a
scraper; contracts/scrapers/_own_site.py reuses the helpers for staffing firms.
"""

import asyncio
import html as html_lib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.base import HTTPScraper, ScrapedJob, ScrapeResult, UnexpectedResponseError

_LD_JSON_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)


class RobotsDisallowed(Exception):
    """robots.txt disallows the page; the scraper must not read it."""


# ----------------------------------------------------------------- helpers --

def soup(markup: str) -> BeautifulSoup:
    return BeautifulSoup(markup or "", "html.parser")


def text_of(node: Any) -> str:
    """Whitespace-collapsed visible text of a BeautifulSoup node (or '')."""
    if node is None:
        return ""
    if isinstance(node, str):
        return re.sub(r"\s+", " ", html_lib.unescape(node)).strip()
    return re.sub(r"\s+", " ", node.get_text(" ")).strip()


def abs_url(base: str, href: Optional[str]) -> str:
    return urljoin(base, (href or "").strip())


def clean_location(*parts: Optional[str]) -> str:
    out = []
    for p in parts:
        p = re.sub(r"\s+", " ", str(p or "")).strip(" ,|-")
        if p and p.lower() not in {x.lower() for x in out}:
            out.append(p)
    return ", ".join(out)


def parse_when(value: Any) -> Optional[datetime]:
    """ISO-8601 (Z / offsets / fractions), epoch seconds or millis, '/Date(ms)/',
    'MM/DD/YYYY', 'Month D, YYYY' -> naive UTC datetime (or None)."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.strip().isdigit()):
        n = int(value)
        try:
            return datetime.fromtimestamp(n / 1000 if n > 10**11 else n, tz=timezone.utc).replace(tzinfo=None)
        except (ValueError, OverflowError, OSError):
            return None
    s = str(value).strip()
    m = re.match(r"/Date\((\d+)", s)
    if m:
        return parse_when(int(m.group(1)))
    iso = s.replace("Z", "+00:00").replace(" ", "T", 1) if re.match(r"\d{4}-\d{2}-\d{2}", s) else None
    if iso:
        iso = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", iso)
        iso = re.sub(r"\.(\d{1,6})\d*", lambda mm: "." + mm.group(1).ljust(6, "0"), iso)
        iso = re.sub(r"([+-]\d{2})$", r"\1:00", iso)
        try:
            dt = datetime.fromisoformat(iso)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except ValueError:
            pass
    for fmt in ("%m/%d/%Y", "%m-%d-%Y", "%d/%m/%Y", "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y",
                "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is not None:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except ValueError:
            continue
    return None


def jsonld_postings(markup: Optional[str]) -> list[dict]:
    """Every schema.org JobPosting object embedded in a page (lists and @graph included)."""
    out: list[dict] = []

    def walk(item: Any) -> None:
        if isinstance(item, list):
            for x in item:
                walk(x)
        elif isinstance(item, dict):
            kind = item.get("@type")
            if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
                out.append(item)
            for key in ("@graph", "itemListElement", "item"):
                if key in item:
                    walk(item[key])

    for block in _LD_JSON_RE.findall(markup or ""):
        try:
            walk(json.loads(block.strip(), strict=False))
        except ValueError:
            continue
    return out


def jsonld_location(posting: dict) -> str:
    """'City, Region, Country' from a JobPosting's jobLocation (first one), or 'Remote'."""
    locs = posting.get("jobLocation") or []
    if isinstance(locs, dict):
        locs = [locs]
    names = []
    for loc in locs:
        addr = (loc or {}).get("address") or {}
        if isinstance(addr, str):
            names.append(addr)
            continue
        country = addr.get("addressCountry")
        if isinstance(country, dict):
            country = country.get("name")
        name = clean_location(addr.get("addressLocality"), addr.get("addressRegion"), country)
        if name and name not in names:
            names.append(name)
    if not names and str(posting.get("jobLocationType", "")).upper() == "TELECOMMUTE":
        return "Remote"
    return " / ".join(names[:3])


def strip_markup(markup: str, keep_json: bool = True) -> str:
    """Drop scripts/styles/svg bodies (keeping ld+json / __NEXT_DATA__ when keep_json):
    used to keep saved test fixtures small."""
    def repl(m):
        tag = m.group(0)
        if keep_json and ("ld+json" in tag[:200] or "__NEXT_DATA__" in tag[:200]):
            return tag
        return ""
    markup = re.sub(r"<script\b.*?</script>", repl, markup, flags=re.S | re.I)
    markup = re.sub(r"<(style|svg|noscript)\b.*?</\1>", "", markup, flags=re.S | re.I)
    return markup


# ------------------------------------------------------------- base class --

class OwnSiteScraper(HTTPScraper):
    """Base for one company's own careers site. Subclasses implement fetch_raw() + parse_job()."""

    MAX_JOBS = 1500          # postings kept per run
    TIME_BUDGET_SECONDS = 55  # stop paging after this (the run is then not complete)
    MIN_INTERVAL = 1.0       # seconds between requests to one host (on top of the shared bucket)
    ROBOTS_FOR_HTML = True   # check robots.txt before every HTML page

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._deadline: Optional[float] = None
        self._last_hit: dict[str, float] = {}
        self.truncated = False  # set when paging stopped early (time / job cap / page cap)

    # -- budget
    def start_clock(self) -> None:
        self._deadline = time.monotonic() + self.TIME_BUDGET_SECONDS

    def out_of_time(self) -> bool:
        if self._deadline is not None and time.monotonic() > self._deadline:
            self.truncated = True
            return True
        return False

    def full(self, items: list) -> bool:
        if len(items) >= self.MAX_JOBS:
            self.truncated = True
            return True
        return False

    # -- network (the one entry point; tests replace it)
    async def _robots_ok(self, url: str) -> bool:
        from services import robots
        return await asyncio.to_thread(robots.allowed, url)

    async def _http(self, method: str, url: str, *, params: Optional[dict] = None, json_body: Any = None,
                    data: Any = None, headers: Optional[dict] = None, expect: str = "json") -> Any:
        """One polite request: robots.txt for HTML pages, per-host pacing, the shared
        host bucket and Retry-After (HTTPScraper._request). Returns JSON or text."""
        if expect == "text" and self.ROBOTS_FOR_HTML and not await self._robots_ok(url):
            raise RobotsDisallowed(url)
        from urllib.parse import urlparse
        host = urlparse(url).netloc
        last = self._last_hit.get(host)
        if last is not None:
            wait = self.MIN_INTERVAL - (time.monotonic() - last)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_hit[host] = time.monotonic()
        kwargs: dict = {"params": params, "headers": dict(headers or {})}
        if json_body is not None:
            kwargs["json"] = json_body
        if data is not None:
            kwargs["data"] = data
        if expect == "text":
            return await self._request(method, url, lambda r: r.text(), **kwargs)
        return await self._request(method, url, lambda r: r.json(content_type=None), **kwargs)

    async def get_json(self, url: str, **kw) -> Any:
        return await self._http("GET", url, **kw)

    async def post_json(self, url: str, body: Any = None, **kw) -> Any:
        return await self._http("POST", url, json_body=body, **kw)

    async def get_text(self, url: str, **kw) -> str:
        return await self._http("GET", url, expect="text", **kw)

    async def get_page_or_none(self, url: str, **kw) -> Optional[str]:
        """An HTML listing page, or None when the site answers 404 (past the last page)."""
        import aiohttp
        try:
            return await self.get_text(url, **kw)
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                return None
            raise

    # -- results
    async def fetch_raw(self) -> list:
        raise NotImplementedError

    def listing_items(self, payload: Any) -> list:
        """Raw postings in one listing response (JSON or HTML); override per site."""
        raise NotImplementedError

    async def scrape(self) -> ScrapeResult:
        self.start_clock()
        self.truncated = False
        try:
            raw = await self.fetch_raw()
        except RobotsDisallowed as e:
            return ScrapeResult(success=False, error_message=f"robots.txt disallows {e}")
        jobs = self.finalize(self.parse_all(raw))
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs),
                            complete=not self.truncated and len(jobs) < self.MAX_JOBS)

    def finalize(self, jobs: Iterable[ScrapedJob]) -> list[ScrapedJob]:
        """Dedupe by external id; keep at most MAX_JOBS (in listing order)."""
        seen, out = set(), []
        for job in jobs:
            if job and job.external_job_id not in seen:
                seen.add(job.external_job_id)
                out.append(job)
        if len(out) > self.MAX_JOBS:
            self.truncated = True
        return out[: self.MAX_JOBS]

    def job(self, *, title: Any, location: Any, job_url: str, external_job_id: Any, **extra) -> Optional[ScrapedJob]:
        """ScrapedJob with the required fields checked (None when one is missing)."""
        title = text_of(str(title or ""))
        ext = str(external_job_id or "").strip()
        if not title or not ext or not job_url:
            return None
        desc = extra.pop("job_description", None)
        if desc and ("<" in desc and ">" in desc):
            desc = self.clean_html(desc)
        return ScrapedJob(title=title, location=text_of(str(location or "")) or "Not specified",
                          job_url=job_url, external_job_id=ext, job_description=desc or None, **extra)

    @staticmethod
    def expect_dict(data: Any, what: str = "response") -> dict:
        if not isinstance(data, dict):
            raise UnexpectedResponseError(f"expected a JSON object for {what}, got {type(data).__name__}")
        return data


# ------------------------------------------------------------- iCIMS Jibe --

class JibeMixin:
    """
    Careers sites on iCIMS Jibe ("careers-home"): GET {BASE}/api/jobs?page=N&limit=100
    returns {"jobs": [{"data": {...}}], "totalCount": n}, newest first, with the
    full description. robots.txt on these hosts allows everything (crawl-delay 5,
    which MIN_INTERVAL honours). Public posting: {BASE}/careers-home/jobs/{req_id}.
    """

    BASE_URL: str = ""
    PAGE_LIMIT = 100
    MIN_INTERVAL = 5.0  # crawl-delay: 5 in the sites' robots.txt
    MAX_PAGES = 15
    TIME_BUDGET_SECONDS = 48  # ~10 pages at the crawl delay: the newest ~1,000 postings

    def listing_items(self, payload: Any) -> list:
        data = self.expect_dict(payload, "jibe /api/jobs")
        return [j.get("data") or j for j in self.expect_list(data, "jobs")]

    async def fetch_raw(self) -> list:
        raw, seen, total = [], set(), None
        for page in range(1, self.MAX_PAGES + 1):
            data = await self.get_json(f"{self.BASE_URL}/api/jobs", params={"page": page, "limit": self.PAGE_LIMIT})
            items = self.listing_items(data)
            total = data.get("totalCount") if total is None else total
            fresh = [i for i in items if (i.get("req_id") or i.get("slug")) not in seen]
            seen.update(i.get("req_id") or i.get("slug") for i in fresh)
            raw.extend(fresh)
            if not fresh or (total is not None and len(seen) >= total):
                break
            if self.full(raw) or self.out_of_time():
                break
        else:
            self.truncated = True
        return raw

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        req = raw.get("req_id") or raw.get("slug")
        location = raw.get("full_location") or raw.get("short_location") or clean_location(
            raw.get("city"), raw.get("state"), raw.get("country"))
        if raw.get("location_name") and "remote" in str(raw.get("location_name")).lower() and "remote" not in location.lower():
            location = f"{location} (Remote)" if location else "Remote"
        desc = "\n".join(p for p in (raw.get("description"), raw.get("responsibilities"), raw.get("qualifications")) if p)
        categories = raw.get("categories") or []
        dept = categories[0].get("name") if categories and isinstance(categories[0], dict) else None
        etype = (raw.get("employment_type") or "").replace("_", "-").lower() or None
        return self.job(
            title=raw.get("title"),
            location=location,
            job_url=f"{self.BASE_URL}/careers-home/jobs/{req}",
            external_job_id=req,
            job_description=desc,
            department=dept or raw.get("department") or None,
            posted_date=parse_when(raw.get("posted_date") or raw.get("create_date")),
            employment_type=etype,
            employment_type_raw=raw.get("employment_type"),
        )
