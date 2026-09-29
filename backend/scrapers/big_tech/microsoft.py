"""
Microsoft Jobs Scraper.

Microsoft moved careers to Eightfold (apply.careers.microsoft.com). The old
gcsservices.careers.microsoft.com search API no longer resolves (TLS hostname
mismatch). The public PCSX search endpoint is a plain GET, 10 results per page.
"""

import asyncio
from datetime import datetime
from typing import Optional

import aiohttp

from scrapers.base import (
    HTTPScraper,
    ScraperConfig,
    ScraperType,
    ScrapedJob,
    ScrapeResult,
)
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="big_tech")
class MicrosoftScraper(HTTPScraper):
    """Scraper for Microsoft careers (Eightfold PCSX)."""

    config = ScraperConfig(
        company_slug="microsoft",
        company_name="Microsoft",
        careers_url="https://apply.careers.microsoft.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        api_url="https://apply.careers.microsoft.com/api/pcsx/search",
    )

    BASE_URL = "https://apply.careers.microsoft.com"
    PAGE_SIZE = 10  # server caps num at 10
    # Newest 500 (~50 requests, ~25s). Eightfold starts answering 429 after
    # ~100 rapid requests, so stay well below that.
    MAX_JOBS = 500

    async def scrape(self) -> ScrapeResult:
        all_jobs = []
        start = 0
        pages = 0
        total = None

        while start < self.MAX_JOBS:
            params = {
                "domain": "microsoft.com",
                "query": "",
                "location": "",
                "start": start,
                "num": self.PAGE_SIZE,
                "sort_by": "timestamp",
            }
            try:
                data = await self.fetch_json(self.config.api_url, params=params)
            except aiohttp.ClientResponseError as e:
                if e.status == 429 and all_jobs:
                    self.logger.warning(f"Rate limited at start={start}; keeping {len(all_jobs)} jobs")
                    break
                raise
            payload = data.get("data") if isinstance(data, dict) else None
            positions = self.expect_list(payload if payload is not None else data, "positions")
            pages += 1
            if total is None:
                total = (payload or {}).get("count") or 0
            if not positions:
                break
            all_jobs.extend(self.parse_all(positions))
            start += len(positions)
            if start >= total:
                break
            await asyncio.sleep(0.3)

        # Paging a newest-first list can repeat rows as new postings land, and
        # one requisition can appear more than once; keep the first of each id.
        seen = set()
        all_jobs = [j for j in all_jobs if not (j.external_job_id in seen or seen.add(j.external_job_id))]
        return ScrapeResult(success=True, jobs=all_jobs, pages_scraped=pages)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            job_id = str(raw.get("id") or "")
            if not job_id:
                return None
            ts = raw.get("postedTs") or raw.get("creationTs")
            path = raw.get("positionUrl") or f"/careers/job/{job_id}"
            work = raw.get("workLocationOption")
            return ScrapedJob(
                title=raw.get("name", ""),
                location="; ".join(raw.get("locations") or []),
                job_url=f"{self.BASE_URL}{path}",
                external_job_id=str(raw.get("displayJobId") or job_id),
                department=raw.get("department") or "",
                posted_date=datetime.utcfromtimestamp(ts) if ts else None,
                remote_type={"remote": "remote", "hybrid": "hybrid", "onsite": "on-site"}.get(work),
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
