"""
Radancy TalentBrew career sites (pure HTTP, no Playwright).

TalentBrew sites (tbcdn.talentbrew.com assets) load search results from
{SITE_URL}/search-jobs/results, which returns JSON whose "results" key is an
HTML fragment of <li><a href="/job/..." data-job-id="..."> entries. Leaving
SearchFiltersModuleName out of the query drops the multi-MB "filters" fragment.

Replaces the disabled Workday scrapers for companies that left Workday.
Verified 2026-09-29.
"""

import asyncio
from typing import List, Optional
from urllib.parse import urljoin

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


class RadancyMixin:
    """
    Scrape a Radancy TalentBrew search-jobs endpoint.

    Subclasses set SITE_URL (site root including any locale prefix, e.g.
    https://jobs.walgreens.com/en). Optional ANCHOR_CLASS keeps only result
    anchors carrying that CSS class (e.g. a brand-facet class).
    """

    SITE_URL: str = ""
    ANCHOR_CLASS: Optional[str] = None
    RECORDS_PER_PAGE = 500
    # Celery soft-kills HTTP scrape tasks at 120s; stay well inside it.
    MAX_JOBS = 1500
    TIME_BUDGET_SECONDS = 75
    MAX_PAGES = 20

    def _results_url(self) -> str:
        return f"{self.SITE_URL.rstrip('/')}/search-jobs/results"

    def _params(self, page: int) -> dict:
        return {
            "ActiveFacetID": "0",
            "CurrentPage": str(page),
            "RecordsPerPage": str(self.RECORDS_PER_PAGE),
            "Distance": "50",
            "RadiusUnitType": "0",
            "ShowRadius": "False",
            "IsPagination": "False" if page == 1 else "True",
            "FacetFilters": "",
            "SearchResultsModuleName": "Search Results",
            "SortCriteria": "0",
            "SortDirection": "0",
            "SearchType": "5",
        }

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        seen = set()
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS
        url = self.resolve_api_url(self._results_url())
        page = 1
        while page <= self.MAX_PAGES:
            data = await self.fetch_json(
                url, params=self._params(page), headers={"X-Requested-With": "XMLHttpRequest"}
            )
            if not isinstance(data, dict) or not isinstance(data.get("results"), str):
                if page == 1:
                    got = sorted(data)[:8] if isinstance(data, dict) else type(data).__name__
                    raise UnexpectedResponseError(f"expected HTML 'results' fragment, got {got}")
                break
            items, total_pages = self.extract_items(data["results"])
            if not items and page == 1 and data.get("hasJobs"):
                raise UnexpectedResponseError("hasJobs=true but no a[data-job-id] result anchors")
            fresh = [i for i in items if i["job_id"] not in seen]
            seen.update(i["job_id"] for i in fresh)
            if self.ANCHOR_CLASS:
                fresh = [i for i in fresh if self.ANCHOR_CLASS in i["classes"]]
            if fresh:
                all_jobs.extend(self.parse_all(fresh))
            if (
                not items
                or page >= (total_pages or page)
                or len(all_jobs) >= self.MAX_JOBS
                or loop.time() > deadline
            ):
                break
            page += 1
            await asyncio.sleep(0.1)
        if len(all_jobs) > self.MAX_JOBS:
            all_jobs = all_jobs[: self.MAX_JOBS]
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def extract_items(self, html: str) -> tuple:
        """Return ([raw item dict], total_pages or None) from a results fragment."""
        soup = BeautifulSoup(html, "lxml")
        total_pages = None
        section = soup.find(id="search-results")
        if section is not None:
            try:
                total_pages = int(section.get("data-total-pages") or 0) or None
            except ValueError:
                total_pages = None
        container = soup.find(id="search-results-list") or soup
        items = []
        for a in container.select("a[data-job-id]"):
            href = a.get("href") or ""
            if "/job/" not in href:
                continue
            title_el = a.find(["h2", "h3"])

            def text(cls):
                el = a.select_one(f".{cls}")
                return el.get_text(" ", strip=True) if el else ""

            items.append({
                "job_id": a["data-job-id"],
                "href": href,
                "classes": a.get("class") or [],
                "title": title_el.get_text(" ", strip=True) if title_el else "",
                "location": text("job-location"),
                "req_id": text("job-id"),
                "work_setting": text("job-worksetting"),
                "category": text("job-category"),
                "date_posted": text("job-date-posted"),
            })
        return items, total_pages

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title")
            href = raw.get("href")
            job_id = raw.get("job_id")
            if not (title and href and job_id):
                return None
            setting = (raw.get("work_setting") or "").lower()
            remote_type = next((t for t in ("remote", "hybrid") if t in setting), None)
            if setting and not remote_type and "site" in setting:
                remote_type = "on-site"
            return ScrapedJob(
                title=title,
                location=raw.get("location") or "",
                job_url=urljoin(self.SITE_URL, href),
                external_job_id=str(job_id),
                department=raw.get("category") or None,
                posted_date=self.parse_date(raw.get("date_posted")) if raw.get("date_posted") else None,
                remote_type=remote_type,
            )
        except Exception as e:
            self.logger.error(f"Error parsing Radancy job: {e}")
            return None


@ScraperRegistry.register(category="enterprise")
class OptumRadancyScraper(RadancyMixin, HTTPScraper):
    """UnitedHealth Group careers site; keeps only Optum-branded postings."""

    config = ScraperConfig(
        company_slug="optum",
        company_name="Optum",
        careers_url="https://careers.unitedhealthgroup.com/search-jobs",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    SITE_URL = "https://careers.unitedhealthgroup.com"
    ANCHOR_CLASS = "brand-facet__optum"


@ScraperRegistry.register(category="enterprise")
class ChipotleRadancyScraper(RadancyMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="chipotle",
        company_name="Chipotle",
        careers_url="https://jobs.chipotle.com/search-jobs",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    SITE_URL = "https://jobs.chipotle.com"


@ScraperRegistry.register(category="enterprise")
class WalgreensRadancyScraper(RadancyMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="walgreens",
        company_name="Walgreens",
        careers_url="https://jobs.walgreens.com/en/search-jobs",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    SITE_URL = "https://jobs.walgreens.com/en"
