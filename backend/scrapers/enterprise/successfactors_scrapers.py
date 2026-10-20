"""
SAP SuccessFactors Career Site Builder scrapers (pure HTTP, no Playwright).

CSB career sites (e.g. jobs.exxonmobil.com) render search results server-side:
GET /search/?q=&startrow={N} returns 25 postings per page as `tr.data-row`
rows (a.jobTitle-link -> /job/{slug}/{id}/, span.jobLocation,
span.jobDepartment, span.jobDate "Sep 29, 2026"). The total is announced in
`.paginationLabel` as "Results 1 – 25 of 575".

Two newer CSB layouts are read too:
- tiles: the same /search/?startrow= pages list postings as `li.job-tile`
  (a.jobTitle-link, "...-desktop-section-location-value" etc.); the total is
  "Showing 1 to 25 of 278 Jobs" (careers.paramount.com, careers.irissoftware.com).
- "unify": the search page only loads a React job-search widget, which reads
  POST /services/recruiting/v1/jobs ({"locale", "pageNumber", "sortBy", ...};
  10 postings a page, {"jobSearchResult": [{"response": {...}}], "totalJobs"}).
  Postings open at /job/{urlTitle}/{id}-{locale}/ (careers.hcltech.com).
  Pages are read newest first until MAX_JOBS or the time budget.
"""

import asyncio
import re
from datetime import datetime
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
# Markers of the "unify" search page, whose results come from the jobs API.
_SF_UNIFY_MARKERS = ("rmk-jobs-search", "jobSearch_searchGridComponent", 'data-testid="submitJobSearchBtn"')
_SF_UNIFY_PAGE_SIZE = 10


def _unify_date(value) -> str:
    """'10/20/26' (the widget's m/d/yy) -> '2026-10-20'; '' when unreadable."""
    try:
        return datetime.strptime(str(value or ""), "%m/%d/%y").strftime("%Y-%m-%d")
    except ValueError:
        return ""


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
    # The unify API serves 10 postings a request, so it gets its own, shorter budget.
    UNIFY_TIME_BUDGET_SECONDS = 50

    @property
    def sf_base_url(self) -> str:
        return f"https://{self.SF_HOST}"

    async def _fetch_sf_page(self, startrow: int) -> str:
        params = {"q": "", "startrow": str(startrow), **self.SEARCH_PARAMS}
        return await self.fetch_html(f"{self.sf_base_url}/search/", params=params)

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS

        first_html = await self._fetch_sf_page(0)
        first = BeautifulSoup(first_html, "html.parser")
        first_rows = self.parse_search_page(first, self.sf_base_url)
        if not first_rows and first.select_one("tr.data-row, .paginationLabel, li.job-tile, #tile-search-results-label") is None:
            if any(marker in first_html for marker in _SF_UNIFY_MARKERS):
                return await self._scrape_unify(min(deadline, loop.time() + self.UNIFY_TIME_BUDGET_SECONDS))
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

    # -- "unify" sites: the job-search widget's JSON API ----------------------

    def _unify_locale(self) -> str:
        return self.SEARCH_PARAMS.get("locale") or "en_US"

    def _unify_body(self, page: int) -> dict:
        return {
            "locale": self._unify_locale(), "pageNumber": page, "sortBy": "date", "keywords": "",
            "location": "", "facetFilters": {}, "brand": "", "skills": [], "categoryId": 0,
            "alertId": "", "rcmCandidateId": "",
        }

    async def _unify_page(self, page: int) -> dict:
        data = await self.fetch_json(f"{self.sf_base_url}/services/recruiting/v1/jobs",
                                     method="POST", json_data=self._unify_body(page))
        if not isinstance(data, dict):
            raise UnexpectedResponseError(f"expected SuccessFactors jobs dict, got {type(data).__name__}")
        return data

    async def _scrape_unify(self, deadline: float) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        first = await self._unify_page(0)
        results = self.expect_list(first, "jobSearchResult")
        total = int(first.get("totalJobs") or 0)
        raw = [self.unify_row(r, self.sf_base_url, self._unify_locale()) for r in results]
        limit = min(total, self.MAX_JOBS)
        pages = list(range(1, -(-limit // _SF_UNIFY_PAGE_SIZE)))
        sem = asyncio.Semaphore(self.CONCURRENCY)
        timed_out = False

        async def fetch(page: int) -> list:
            nonlocal timed_out
            async with sem:
                if loop.time() > deadline:
                    timed_out = True
                    return []
                data = await self._unify_page(page)
                return [self.unify_row(r, self.sf_base_url, self._unify_locale())
                        for r in data.get("jobSearchResult") or []]

        for rows in await asyncio.gather(*(fetch(p) for p in pages)):
            raw.extend(rows)
        seen, unique = set(), []
        for r in raw:
            if r and r["id"] not in seen:
                seen.add(r["id"])
                unique.append(r)
        jobs = self.parse_all(unique[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=1 + len(pages),
                            complete=not timed_out and total <= self.MAX_JOBS and len(unique) >= total)

    @staticmethod
    def unify_row(result: dict, base_url: str, locale: str = "en_US") -> Optional[dict]:
        """One jobSearchResult entry as the raw dict parse_job reads."""
        job = (result or {}).get("response") or {}
        job_id = str(job.get("id") or "").strip()
        title = job.get("unifiedStandardTitle") or job.get("title") or ""
        if not job_id or not title:
            return None
        url_title = job.get("unifiedUrlTitle") or job.get("urlTitle") or "job"

        def values(*keys_like: str) -> list:
            out = []
            for key, value in job.items():
                if any(k in key.lower() for k in keys_like):
                    for v in (value if isinstance(value, list) else [value]):
                        v = str(v or "").strip()
                        if v and v.lower() not in ("others", "other", "n/a") and v not in out:
                            out.append(v)
            return out

        location = (values("joblocationshort") or [""])[0] or ", ".join(
            values("city") + values("state") + values("country"))
        return {
            "id": job_id,
            "title": title,
            "url": f"{base_url}/job/{url_title}/{job_id}-{locale}/",
            "location": location,
            "department": (values("department", "category") or [""])[0],
            "date": _unify_date(job.get("unifiedStandardStart")),
        }

    @staticmethod
    def sf_total(soup: BeautifulSoup) -> Optional[int]:
        label = soup.select_one(".paginationLabel") or soup.select_one("#tile-search-results-label")
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
        for tile in soup.select("li.job-tile"):
            link = tile.select_one("a.jobTitle-link[href]")
            href = urljoin(base_url + "/", (link.get("href") if link else None) or tile.get("data-url") or "")
            m = _SF_JOB_ID_RE.search(href)
            if not link or not m:
                continue

            def field(name: str) -> str:
                el = tile.select_one(f'[id$="-desktop-section-{name}-value"]') or tile.select_one(
                    f'[id$="-section-{name}-value"]')
                return el.get_text(" ", strip=True) if el else ""

            out.append({
                "id": m.group(1),
                "title": link.get_text(" ", strip=True),
                "url": href,
                "location": field("location") or field("city"),
                "department": field("dept") or field("department"),
                "date": field("date"),
                "shift_type": field("shifttype"),
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
