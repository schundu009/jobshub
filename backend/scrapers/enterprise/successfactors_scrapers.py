"""
SAP SuccessFactors Career Site Builder scrapers (pure HTTP, no Playwright).

CSB career sites (e.g. jobs.exxonmobil.com) render search results server-side:
GET /search/?q=&startrow={N} returns 25 postings per page as `tr.data-row`
rows (a.jobTitle-link -> /job/{slug}/{id}/, span.jobLocation,
span.jobDepartment, span.jobDate "Sep 29, 2026"). The total is announced in
`.paginationLabel` as "Results 1 – 25 of 575".
"""

import asyncio
import re
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

_SF_JOB_ID_RE = re.compile(r"/job/[^?#]*?/(\d+)/?(?:[?#]|$)")
_SF_TOTAL_RE = re.compile(r"of\s+([\d,]+)")


class SuccessFactorsMixin:
    """
    Subclasses set SF_HOST (e.g. "jobs.exxonmobil.com").

    Optional: SEARCH_PARAMS (extra query args such as {"locale": "en_US"}),
    PAGE_SIZE (CSB default 25), MAX_JOBS, TIME_BUDGET_SECONDS, CONCURRENCY.
    """

    SF_HOST: str = ""
    SEARCH_PARAMS: dict = {}
    PAGE_SIZE = 25
    MAX_JOBS = 2500
    TIME_BUDGET_SECONDS = 75
    CONCURRENCY = 4

    @property
    def sf_base_url(self) -> str:
        return f"https://{self.SF_HOST}"

    async def _fetch_sf_page(self, startrow: int) -> str:
        params = {"q": "", "startrow": str(startrow), **self.SEARCH_PARAMS}
        return await self.fetch_html(f"{self.sf_base_url}/search/", params=params)

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS

        first = BeautifulSoup(await self._fetch_sf_page(0), "html.parser")
        first_rows = self.parse_search_page(first, self.sf_base_url)
        if not first_rows and first.select_one("tr.data-row, .paginationLabel") is None:
            raise UnexpectedResponseError("no SuccessFactors result table on search page")
        total = self.sf_total(first)
        page_size = len(first_rows) or self.PAGE_SIZE

        raw_jobs: List[dict] = list(first_rows)
        seen = {r["id"] for r in first_rows}
        pages_scraped = 1
        limit = min(total if total is not None else self.MAX_JOBS, self.MAX_JOBS)
        startrows = list(range(page_size, limit, page_size))

        sem = asyncio.Semaphore(self.CONCURRENCY)

        async def fetch(startrow: int) -> List[dict]:
            if loop.time() > deadline:
                return []
            async with sem:
                if loop.time() > deadline:
                    return []
                html = await self._fetch_sf_page(startrow)
                return self.parse_search_page(BeautifulSoup(html, "html.parser"), self.sf_base_url)

        if total is not None:
            pages = await asyncio.gather(*(fetch(s) for s in startrows))
        else:
            # Unknown total: walk sequentially until a page adds nothing new.
            pages = []
            for s in startrows:
                rows = await fetch(s)
                if not rows or all(r["id"] in seen for r in rows):
                    break
                seen.update(r["id"] for r in rows)
                pages.append(rows)
            seen = {r["id"] for r in first_rows}

        for rows in pages:
            if rows:
                pages_scraped += 1
            for r in rows:
                if r["id"] not in seen:
                    seen.add(r["id"])
                    raw_jobs.append(r)

        jobs = self.parse_all(raw_jobs[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=pages_scraped)

    @staticmethod
    def sf_total(soup: BeautifulSoup) -> Optional[int]:
        label = soup.select_one(".paginationLabel")
        if not label:
            return None
        m = _SF_TOTAL_RE.search(label.get_text(" ", strip=True))
        return int(m.group(1).replace(",", "")) if m else None

    @staticmethod
    def parse_search_page(soup: BeautifulSoup, base_url: str) -> List[dict]:
        out = []
        for row in soup.select("tr.data-row"):
            link = row.select_one("a.jobTitle-link[href]")
            if not link:
                continue
            href = urljoin(base_url + "/", link["href"])
            m = _SF_JOB_ID_RE.search(href)
            if not m:
                continue

            def text(sel: str) -> str:
                el = row.select_one(sel)
                return el.get_text(" ", strip=True) if el else ""

            out.append({
                "id": m.group(1),
                "title": link.get_text(" ", strip=True),
                "url": href,
                "location": text("td.colLocation .jobLocation") or text(".jobLocation"),
                "department": text("td.colDepartment .jobDepartment") or text(".jobDepartment"),
                "date": text("td.colDate .jobDate") or text(".jobDate"),
                "shift_type": text(".jobShifttype"),
            })
        return out

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = self.clean_text(raw.get("title"))
            if not title:
                return None
            return ScrapedJob(
                title=title,
                location=raw.get("location", ""),
                job_url=raw["url"],
                external_job_id=raw["id"],
                department=raw.get("department") or None,
                posted_date=self.parse_date(raw.get("date")),
                raw_data=raw,
            )
        except Exception as e:
            self.logger.error(f"Error parsing SuccessFactors job: {e}")
            return None


@ScraperRegistry.register(category="enterprise")
class ExxonMobilSuccessFactorsScraper(SuccessFactorsMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="exxonmobil",
        company_name="ExxonMobil",
        careers_url="https://jobs.exxonmobil.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=100,
    )
    SF_HOST = "jobs.exxonmobil.com"
