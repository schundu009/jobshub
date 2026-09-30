"""
Phenom People career sites (pure HTTP, no Playwright).

Phenom sites embed their config and the first page of results in the
search-results HTML (``phApp.ddo = {...}``, key ``eagerLoadRefineSearch``).
The same search is served as JSON by ``POST {host}/widgets`` with
``ddoKey: "refineSearch"``, which accepts page sizes of 100+, so a board is
read in a handful of requests. The widget payload needs the site's refNum,
locale, country and pageId, which are read from the search-results page. If
the widgets call is rejected, the scraper falls back to paging the HTML
(``?from=N&s=1``, 10-20 jobs per page).

Public job pages: {SITE_URL}/job/{jobId}/{title-slug}.

Replaces the disabled Workday scrapers for companies that left Workday.
Verified 2026-09-29.
"""

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import List, Optional, Tuple
from urllib.parse import urlparse

from scrapers.base import (
    HTTPScraper,
    ScrapedJob,
    ScraperConfig,
    ScraperType,
    ScrapeResult,
    UnexpectedResponseError,
)
from scrapers.registry import ScraperRegistry

_DDO_RE = re.compile(r"phApp\.ddo\s*=\s*(\{.*?\});\s*phApp\.", re.S)
_SLUG_RE = re.compile(r"[^0-9A-Za-z]+")


def _phenom_setting(html: str, key: str) -> Optional[str]:
    """First ``"key":"value"`` in the page (the phApp config comes first)."""
    m = re.search(r'"%s"\s*:\s*"([^"]*)"' % re.escape(key), html)
    return m.group(1) if m else None


def parse_phenom_ddo(html: str) -> dict:
    """Return the phApp.ddo object embedded in a Phenom page ({} if absent)."""
    m = _DDO_RE.search(html)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except ValueError:
        return {}


def _parse_phenom_date(value: Optional[str]) -> Optional[datetime]:
    """'2026-07-29T21:36:55.608+0000' -> naive UTC datetime."""
    if not value:
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(value, fmt).astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            continue
    return None


class PhenomMixin:
    """
    Scrape a Phenom career site via its /widgets refineSearch API.

    Subclasses set SITE_URL to the site root including country and language,
    e.g. https://careers.dhl.com/global/en.
    """

    SITE_URL: str = ""
    PAGE_SIZE = 100
    # Phenom search is Elasticsearch-backed: from + size must stay <= 10,000.
    RESULT_WINDOW = 10000
    # Celery soft-kills HTTP scrape tasks at 120s; stay well inside it.
    MAX_JOBS = 2000
    TIME_BUDGET_SECONDS = 60

    def _host(self) -> str:
        u = urlparse(self.SITE_URL)
        return f"{u.scheme}://{u.netloc}"

    def _search_url(self) -> str:
        return f"{self.SITE_URL.rstrip('/')}/search-results"

    def _widget_payload(self, settings: dict, offset: int, size: Optional[int] = None) -> dict:
        return {
            "lang": settings["locale"],
            "deviceType": "desktop",
            "country": settings["country"],
            "pageName": "search-results",
            "ddoKey": "refineSearch",
            "sortBy": "",
            "subsearch": "",
            "from": offset,
            "jobs": True,
            "counts": False,
            "all_fields": [],
            "size": size or self.PAGE_SIZE,
            "clearAll": False,
            "jdsource": "facets",
            "isSliderEnable": False,
            "pageId": settings["pageId"],
            "siteType": "external",
            "keywords": "",
            "global": True,
            "selected_fields": {},
            "locationData": {},
            "refNum": settings["refNum"],
        }

    @staticmethod
    def _unpack(search: dict) -> Tuple[list, Optional[int]]:
        if not isinstance(search, dict):
            raise UnexpectedResponseError(f"expected refineSearch dict, got {type(search).__name__}")
        data = search.get("data")
        jobs = data.get("jobs") if isinstance(data, dict) else None
        if not isinstance(jobs, list):
            got = sorted(search)[:8]
            raise UnexpectedResponseError(f"expected refineSearch.data.jobs list, got keys={got}")
        return jobs, search.get("totalHits")

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id = str(raw.get("jobId") or raw.get("reqId") or "").strip()
        title = (raw.get("title") or "").strip()
        if not job_id or not title:
            return None
        slug = _SLUG_RE.sub("-", title).strip("-")
        location = raw.get("location") or raw.get("cityStateCountry") or ""
        if not location and raw.get("multi_location"):
            location = raw["multi_location"][0]
        categories = raw.get("multi_category") or []
        department = raw.get("category") or (categories[0] if categories else None)
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"{self.SITE_URL.rstrip('/')}/job/{job_id}/{slug}".rstrip("/"),
            external_job_id=job_id,
            department=department,
            posted_date=_parse_phenom_date(raw.get("postedDate") or raw.get("dateCreated")),
            employment_type=raw.get("type") or raw.get("workHours") or None,
        )

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS

        html = await self.fetch_html(self._search_url())
        ddo = parse_phenom_ddo(html)
        first_jobs, total = self._unpack(ddo.get("eagerLoadRefineSearch"))
        settings = {k: _phenom_setting(html, k) for k in ("refNum", "locale", "country", "pageId")}

        all_jobs: List[ScrapedJob] = []
        seen = set()

        def add(raw_jobs: list) -> int:
            fresh = []
            for raw in raw_jobs:
                key = raw.get("jobSeqNo") or raw.get("jobId")
                if key and key not in seen:
                    seen.add(key)
                    fresh.append(raw)
            all_jobs.extend(self.parse_all(fresh))
            return len(fresh)

        pages = 1
        use_widgets = all(settings.values())
        if use_widgets:
            offset = 0
            while True:
                # A page reaching past totalHits (or the result window) comes
                # back empty, so never ask for more than remains.
                size = min(self.PAGE_SIZE, self.MAX_JOBS - offset, self.RESULT_WINDOW - offset)
                if total:
                    size = min(size, total - offset)
                try:
                    data = await self.fetch_json(
                        f"{self._host()}/widgets",
                        method="POST",
                        json_data=self._widget_payload(settings, offset, size),
                    )
                    search = data.get("refineSearch") if isinstance(data, dict) else data
                    if offset == 0:
                        jobs, total = self._unpack(search)
                    else:
                        jobs = ((search or {}).get("data") or {}).get("jobs") or []
                except Exception as e:
                    if offset == 0:
                        self.logger.warning(f"Phenom widgets API failed, paging HTML instead: {e}")
                        use_widgets = False
                        break
                    raise
                pages += 1
                if not jobs or add(jobs) == 0:
                    break
                offset += len(jobs)
                if (
                    (total is not None and offset >= total)
                    or offset >= min(self.MAX_JOBS, self.RESULT_WINDOW)
                ):
                    break
                if loop.time() > deadline:
                    self.logger.info(f"Phenom: stopping at {len(all_jobs)} jobs (time budget)")
                    break
                await asyncio.sleep(0.2)

        if not use_widgets:
            add(first_jobs)
            offset = len(first_jobs)
            while first_jobs and offset < min(total or 0, self.MAX_JOBS) and loop.time() < deadline:
                page_html = await self.fetch_html(self._search_url(), params={"from": str(offset), "s": "1"})
                jobs, _ = self._unpack(parse_phenom_ddo(page_html).get("eagerLoadRefineSearch"))
                pages += 1
                if not jobs or add(jobs) == 0:
                    break
                offset += len(jobs)
                await asyncio.sleep(0.2)

        return ScrapeResult(
            success=True, jobs=all_jobs, jobs_found=len(all_jobs), pages_scraped=pages
        )


@ScraperRegistry.register(category="enterprise")
class DHLScraper(PhenomMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="dhl",
        company_name="DHL",
        careers_url="https://careers.dhl.com/global/en/search-results",
        scraper_type=ScraperType.HTTP,
    )
    # ~10,000 postings (applications go to dpdhlgroup.avature.net). Capped like
    # the Workday boards so one run doesn't write ~10k rows.
    SITE_URL = "https://careers.dhl.com/global/en"
    PAGE_SIZE = 500
    MAX_JOBS = 1500


@ScraperRegistry.register(category="enterprise")
class BAESystemsScraper(PhenomMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="bae",
        company_name="BAE Systems",
        careers_url="https://jobs.baesystems.com/global/en/search-results",
        scraper_type=ScraperType.HTTP,
    )
    SITE_URL = "https://jobs.baesystems.com/global/en"
    MAX_JOBS = 3000


@ScraperRegistry.register(category="enterprise")
class FranklinTempletonScraper(PhenomMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="franklintempleton",
        company_name="Franklin Templeton",
        careers_url="https://careers.franklintempleton.com/us/en/search-results",
        scraper_type=ScraperType.HTTP,
    )
    SITE_URL = "https://careers.franklintempleton.com/us/en"
