"""
IBM Jobs Scraper.

careers.ibm.com/api/jobs no longer exists. The careers site searches through IBM's
public search service (www-api.ibm.com/search/api/v2, appId=careers), a read-only
POST returning Elasticsearch-style hits. Verified 2026-09-29.
"""

import re
from typing import Optional

from scrapers.base import (
    HTTPScraper,
    ScraperConfig,
    ScraperType,
    ScrapedJob,
    ScrapeResult,
)
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="enterprise")
class IBMScraper(HTTPScraper):
    """Scraper for IBM careers (IBM search API)."""

    config = ScraperConfig(
        company_slug="ibm",
        company_name="IBM",
        careers_url="https://www.ibm.com/careers/search",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        api_url="https://www-api.ibm.com/search/api/v2",
    )

    PAGE_SIZE = 100
    MAX_JOBS = 2500
    SOURCE_FIELDS = [
        "_id", "title", "url", "description", "dcdate",
        "field_keyword_08",  # job category
        "field_keyword_17",  # work arrangement (Hybrid / Remote / On-site)
        "field_keyword_18",  # experience level
        "field_keyword_19",  # location
    ]

    async def scrape(self) -> ScrapeResult:
        all_jobs = []
        offset = 0
        pages = 0
        while offset < self.MAX_JOBS:
            body = {
                "appId": "careers",
                "scopes": ["careers2"],
                "query": {"bool": {"must": []}},
                "size": self.PAGE_SIZE,
                "from": offset,
                "sort": [{"dcdate": "desc"}, {"_score": "desc"}],
                "lang": "zz",
                "sm": {"query": "", "lang": "zz"},
                "_source": self.SOURCE_FIELDS,
            }
            data = await self.fetch_json(self.config.api_url, method="POST", json_data=body)
            hits = self.expect_list((data or {}).get("hits") or {}, "hits")
            pages += 1
            if not hits:
                break
            all_jobs.extend(self.parse_all(hits))
            total = ((data.get("hits") or {}).get("total") or {}).get("value") or 0
            offset += len(hits)
            if offset >= total or len(hits) < self.PAGE_SIZE:
                break

        seen = set()
        all_jobs = [j for j in all_jobs if not (j.external_job_id in seen or seen.add(j.external_job_id))]
        return ScrapeResult(success=True, jobs=all_jobs, pages_scraped=pages)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            src = raw.get("_source") or {}
            url = src.get("url") or ""
            title = src.get("title") or ""
            if not url or not title:
                return None
            m = re.search(r"jobId=(\d+)", url)
            arrangement = (src.get("field_keyword_17") or "").lower()
            return ScrapedJob(
                title=title,
                location=src.get("field_keyword_19") or "",
                job_url=url,
                external_job_id=m.group(1) if m else raw.get("_id", ""),
                job_description=src.get("description") or None,
                department=src.get("field_keyword_08") or "",
                posted_date=self.parse_date(src.get("dcdate") or ""),
                remote_type=("remote" if "remote" in arrangement else
                             "hybrid" if "hybrid" in arrangement else
                             "on-site" if arrangement else None),
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job: {e}")
            return None
