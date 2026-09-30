"""
Avature career portals (pure HTTP, no Playwright).

Avature portals render search results server-side at
{PORTAL_URL}/SearchJobs/?<offset param>=N as <article class="article--result">
cards linking to .../JobDetail/[slug/]<id>. The page size is fixed by the
portal template (Siemens 6, Lululemon 10) and the offset parameter name varies
(jobOffset / folderOffset), so both are read from page 1 (card count and the
"Next" link). The /SearchJobs/feed/ RSS only ever returns the newest 20 jobs,
so it is not used.

Results are newest first; pages are fetched a few at a time until the portal
runs out of results, MAX_JOBS is reached, or the time budget is spent.

Replaces the disabled Workday scrapers for companies that left Workday.
Verified 2026-09-29.
"""

import asyncio
import re
import ssl
from typing import List, Optional
from urllib.parse import parse_qs, urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from scrapers.base import (
    HTTPScraper,
    ScrapedJob,
    ScraperConfig,
    ScraperType,
    ScrapeResult,
    UnexpectedResponseError,
)
from scrapers.registry import ScraperRegistry

_JOB_ID_RE = re.compile(r"/JobDetail/(?:[^?#]*/)?(\d+)(?:[/?#]|$)")


def _text(node) -> str:
    return " ".join(node.get_text(" ", strip=True).split()) if node else ""


class AvatureMixin:
    """
    Scrape an Avature portal's server-rendered SearchJobs pages.

    Subclasses set PORTAL_URL (locale + portal path, e.g.
    https://careers.lululemon.com/en_US/careers). LOCATION_REVERSED turns a
    "Country · State · City" subtitle into "City, State, Country".
    """

    PORTAL_URL: str = ""
    DEFAULT_OFFSET_PARAM = "jobOffset"
    LOCATION_REVERSED = False
    CONCURRENCY = 3
    # Celery soft-kills HTTP scrape tasks at 120s; stay well inside it.
    MAX_JOBS = 1500
    TIME_BUDGET_SECONDS = 60
    MAX_PAGES = 400

    def _search_url(self) -> str:
        return f"{self.PORTAL_URL.rstrip('/')}/SearchJobs/"

    # -- HTML parsing -------------------------------------------------------

    def _extract_rows(self, html: str) -> List[dict]:
        """Return one raw dict per job card on a SearchJobs page."""
        soup = BeautifulSoup(html, "lxml")
        base = self._search_url()
        rows = []
        cards = soup.select("article.article--result")
        for card in cards:
            link = card.select_one("h3 a[href*='JobDetail']") or card.select_one("a[href*='JobDetail']")
            if not link:
                continue
            url = urljoin(base, link.get("href", ""))
            m = _JOB_ID_RE.search(url)
            loc_node = card.select_one(".list-item-location")
            if loc_node:
                parts = [
                    _text(s) for s in loc_node.find_all("span")
                    if "separator" not in (s.get("class") or [])
                ]
                location = ", ".join(p for p in parts if p) or _text(loc_node)
            else:
                sub = card.select_one(".article__header__text__subtitle span") or card.select_one(
                    ".article__header__text__subtitle"
                )
                parts = [p.strip() for p in _text(sub).split("·") if p.strip()]
                if self.LOCATION_REVERSED:
                    parts.reverse()
                location = ", ".join(parts)
            rows.append({
                "title": _text(link),
                "url": url,
                "id": m.group(1) if m else "",
                "location": location,
                "department": _text(card.select_one(".list-item-family")) or None,
            })
        return rows

    def _paging_info(self, html: str) -> Optional[str]:
        """Name of the offset query parameter used by the page's Next link, if any."""
        soup = BeautifulSoup(html, "lxml")
        nxt = soup.select_one(".paginationNextLink a[href], a.paginationNextLink[href]")
        if not nxt:
            return None
        query = parse_qs(urlparse(nxt["href"].replace("&amp;", "&")).query)
        for name in query:
            if name.lower().endswith("offset"):
                return name
        return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        title = (raw.get("title") or "").strip()
        job_id = raw.get("id") or ""
        if not title or not job_id:
            return None
        return ScrapedJob(
            title=title,
            location=raw.get("location") or "",
            job_url=raw.get("url") or "",
            external_job_id=str(job_id),
            department=raw.get("department"),
        )

    # -- scraping -----------------------------------------------------------

    async def _page_session(self) -> aiohttp.ClientSession:
        """
        A cookie-less session for result pages. Avature locks the server-side
        session per cookie, so requests sharing one cookie are served one at a
        time; without a cookie each page is served independently.
        """
        existing = getattr(self, "_avature_session", None)
        if existing is not None and not existing.closed:
            return existing
        base = await self.get_session()
        ctx = ssl.create_default_context()
        try:
            import certifi
            ctx.load_verify_locations(certifi.where())
        except ImportError:
            pass
        self._avature_session = aiohttp.ClientSession(
            headers=dict(base.headers),
            timeout=base.timeout,
            cookie_jar=aiohttp.DummyCookieJar(),
            connector=aiohttp.TCPConnector(ssl=ctx, limit_per_host=self.CONCURRENCY),
        )
        return self._avature_session

    async def _fetch_page(self, offset_param: str, offset: int) -> str:
        session = await self._page_session()
        async with session.get(self._search_url(), params={offset_param: str(offset)}) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def close(self):
        session = getattr(self, "_avature_session", None)
        if session is not None and not session.closed:
            await session.close()
        await super().close()

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS

        first = await self.fetch_html(self._search_url())
        rows = self._extract_rows(first)
        if not rows:
            raise UnexpectedResponseError("Avature SearchJobs page had no job cards")
        page_size = len(rows)
        offset_param = self._paging_info(first)

        all_jobs: List[ScrapedJob] = []
        seen = set()

        def add(page_rows) -> int:
            fresh = [r for r in page_rows if r.get("id") and r["id"] not in seen]
            for r in fresh:
                seen.add(r["id"])
            all_jobs.extend(self.parse_all(fresh))
            return len(fresh)

        add(rows)
        pages = 1
        offset = page_size
        done = offset_param is None  # no Next link: single page of results
        offset_param = offset_param or self.DEFAULT_OFFSET_PARAM
        while not done:
            if len(all_jobs) >= self.MAX_JOBS or pages >= self.MAX_PAGES or loop.time() > deadline:
                self.logger.info(f"Avature: stopping at {len(all_jobs)} jobs (cap/time budget)")
                break
            offsets = [offset + i * page_size for i in range(self.CONCURRENCY)]
            results = await asyncio.gather(
                *(self._fetch_page(offset_param, o) for o in offsets), return_exceptions=True
            )
            failures = 0
            for res in results:
                if isinstance(res, Exception):
                    failures += 1
                    self.logger.warning(f"Avature page fetch failed: {res}")
                    continue
                page_rows = self._extract_rows(res)
                if not page_rows or add(page_rows) == 0:
                    done = True  # past the last page
            if failures == len(results):
                break
            pages += len(offsets)
            offset = offsets[-1] + page_size
            await asyncio.sleep(0.2)

        return ScrapeResult(
            success=True, jobs=all_jobs, jobs_found=len(all_jobs), pages_scraped=pages
        )


@ScraperRegistry.register(category="enterprise")
class SiemensScraper(AvatureMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="siemens",
        company_name="Siemens",
        careers_url="https://jobs.siemens.com/en_US/externaljobs/SearchJobs",
        scraper_type=ScraperType.HTTP,
        # Siemens serves 6 jobs per page and takes ~3s (up to ~15s) per page,
        # so a run covers the newest several hundred of ~2,000 postings within
        # the time budget (newest first; missing jobs are not deactivated).
        request_timeout=20,
    )
    PORTAL_URL = "https://jobs.siemens.com/en_US/externaljobs"
    CONCURRENCY = 6
    TIME_BUDGET_SECONDS = 50


@ScraperRegistry.register(category="enterprise")
class LululemonScraper(AvatureMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="lululemon",
        company_name="Lululemon",
        careers_url="https://careers.lululemon.com/en_US/careers/SearchJobs",
        scraper_type=ScraperType.HTTP,
    )
    PORTAL_URL = "https://careers.lululemon.com/en_US/careers"
    LOCATION_REVERSED = True
    # ~1,900 postings at 10 per page, ~1s per page
    CONCURRENCY = 5
    MAX_JOBS = 2500
