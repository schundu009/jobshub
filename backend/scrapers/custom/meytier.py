"""Meytier - meytier.com/jobs-search (own JSON API).

The jobs-search page posts to https://api-uat-trip.meytier.com/portalUniversalSearch/search
(the host name is the site's own production API despite "uat"); each hit carries
job_metadata with the title, locations and the page path. Posting page:
https://meytier.com/job/<jobUrl>. The page sends Origin/Referer meytier.com, as here.
Verified 2026-10-20 (12 postings).
"""

from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, parse_when
from scrapers.registry import ScraperRegistry

API_URL = "https://api-uat-trip.meytier.com/portalUniversalSearch/search"
BODY = {"q": None, "allSearchTokensArray": [], "cityHexes": None, "stateCodes": None,
        "countryCodes": None, "locationIds": None}


@ScraperRegistry.register(category="custom")
class MeytierScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="meytier",
        company_name="Meytier",
        careers_url="https://meytier.com/jobs-search",
        scraper_type=ScraperType.HTTP,
    )

    def listing_items(self, payload: Any) -> list:
        return self.expect_list(self.expect_dict(payload), "data")

    async def fetch_raw(self) -> list:
        data = await self.post_json(API_URL, BODY, headers={"Origin": "https://meytier.com",
                                                            "Referer": "https://meytier.com/"})
        return self.listing_items(data)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        meta = raw.get("job_metadata") or {}
        locs = meta.get("locations") or []
        location = meta.get("locationDisplay") or (locs[0].get("text") if locs and isinstance(locs[0], dict) else "")
        client = None if raw.get("isClientConfidential") else meta.get("clientName")
        job = self.job(
            title=meta.get("portalJobTitle") or meta.get("jobTitle"),
            location=location,
            job_url=f"https://meytier.com/job/{meta.get('jobUrl')}",
            external_job_id=raw.get("job_id") or raw.get("id"),
            department=", ".join(meta.get("hiringFunction") or []) or None,
            posted_date=parse_when(meta.get("portalPublishDate") or raw.get("updated_at")),
        )
        if job:
            if client:
                job.extra["end_client"] = client
            if meta.get("keywords"):
                job.extra["skills"] = list(meta["keywords"])[:20]
        return job
