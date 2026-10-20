"""HTC Global Services - www.htcinc.com US job listing (own JSON proxy).

The careers-job-listing-us page reads
GET https://www.htcinc.com/wp-content/themes/himalayas-child/job-api-proxy-us.php
(data.jobs, ~110 US postings, truncated descriptions). Posting page:
https://www.htcinc.com/job-detail/?jobcode=<requisition_number>. Verified 2026-10-20.
"""

from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, clean_location, parse_when
from scrapers.registry import ScraperRegistry

API_URL = "https://www.htcinc.com/wp-content/themes/himalayas-child/job-api-proxy-us.php"
LISTING = "https://www.htcinc.com/careers-job-listing-us/"


@ScraperRegistry.register(category="custom")
class HTCGlobalScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="htcglobal",
        company_name="HTC Global Services",
        careers_url=LISTING,
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )

    def listing_items(self, payload: Any) -> list:
        data = self.expect_dict(self.expect_dict(payload).get("data"), "data")
        return self.expect_list(data, "jobs")

    async def fetch_raw(self) -> list:
        return self.listing_items(await self.get_json(API_URL, headers={"Referer": LISTING}))

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        req = raw.get("requisition_number")
        return self.job(
            title=raw.get("job_title"),
            location=clean_location(raw.get("location_name"), raw.get("state_code"), "United States"),
            job_url=f"https://www.htcinc.com/job-detail/?jobcode={req}",
            external_job_id=req,
            job_description=raw.get("job_description"),
            posted_date=parse_when(raw.get("posted_date")),
        )
