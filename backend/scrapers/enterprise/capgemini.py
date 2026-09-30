"""
Capgemini (pure HTTP, no Playwright).

The job search on capgemini.com is a front end for Capgemini's own
"jobstream" API (Azure), found from the page's XHR:

    GET https://cg-jobstream-api.azurewebsites.net/api/job-search?page=N&size=M
    -> {"count": 6886, "data": [{id, ref, source, title, location,
                                 country_code, brand, updated_at, ...}]}

It covers every Capgemini brand (Capgemini, Capgemini Engineering, Invent,
Sogeti, frog) and every country. The API has no posting date (updated_at and
indexed_at are re-index times shared by the whole board), so posted_date is
left unset. Public job pages are
https://www.capgemini.com/jobs/{ref}+{source lowercased}, e.g.
/jobs/558017-en_US+sap_btp (an unknown ref returns 404).

Replaces the disabled Workday scraper (Capgemini left Workday).
Verified 2026-09-29.
"""

import asyncio
from typing import List, Optional

from scrapers.base import (
    HTTPScraper,
    ScrapedJob,
    ScraperConfig,
    ScraperType,
    ScrapeResult,
)
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="enterprise")
class CapgeminiScraper(HTTPScraper):
    config = ScraperConfig(
        company_slug="capgemini",
        company_name="Capgemini",
        careers_url="https://www.capgemini.com/careers/join-capgemini/job-search/",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    API_URL = "https://cg-jobstream-api.azurewebsites.net/api/job-search"
    JOB_URL = "https://www.capgemini.com/jobs/{ref}+{source}"
    PAGE_SIZE = 500  # ~7 MB per page (descriptions included), ~2-3s
    MAX_JOBS = 1500
    # Celery soft-kills HTTP scrape tasks at 120s; stay well inside it.
    TIME_BUDGET_SECONDS = 60

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        title = (raw.get("title") or "").strip()
        ref = (raw.get("ref") or "").strip()
        source = (raw.get("source") or "").strip().lower()
        job_id = str(raw.get("id") or raw.get("_id") or "").strip()
        if not title or not ref or not source or not job_id:
            return None
        return ScrapedJob(
            title=title,
            location=(raw.get("location") or "").strip(),
            job_url=self.JOB_URL.format(ref=ref, source=source),
            external_job_id=job_id,
            job_description=raw.get("description") or None,
            department=raw.get("professional_communities") or raw.get("brand") or None,
            employment_type=raw.get("contract_type") or None,
        )

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS
        api_url = self.resolve_api_url(self.API_URL)

        all_jobs: List[ScrapedJob] = []
        seen = set()
        page = 1
        total = None
        while True:
            data = await self.fetch_json(api_url, params={"page": page, "size": self.PAGE_SIZE})
            raw_jobs = self.expect_list(data, "data") if page == 1 else ((data or {}).get("data") or [])
            if page == 1 and isinstance(data, dict):
                total = data.get("count")
            fresh = []
            for raw in raw_jobs:
                key = raw.get("id") or raw.get("_id")
                if key and key not in seen:
                    seen.add(key)
                    fresh.append(raw)
            all_jobs.extend(self.parse_all(fresh))
            if len(raw_jobs) < self.PAGE_SIZE or not fresh:
                break
            if total is not None and page * self.PAGE_SIZE >= total:
                break
            if len(all_jobs) >= self.MAX_JOBS or loop.time() > deadline:
                self.logger.info(f"Capgemini: stopping at {len(all_jobs)} jobs (cap/time budget)")
                break
            page += 1
            await asyncio.sleep(0.2)

        return ScrapeResult(
            success=True, jobs=all_jobs, jobs_found=len(all_jobs), pages_scraped=page
        )
