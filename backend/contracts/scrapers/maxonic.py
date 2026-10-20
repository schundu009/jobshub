"""
Maxonic.

Endpoint: ``GET https://maxonic.com/api/jobs.php`` - the JSON its own jobs page
(maxonic.com/jobs/) loads: a copy of its Ceipal postings (id, title, city,
state, remote, type, posted, applyUrl to Ceipal's candidate portal), so no
browser is needed. Verified 2026-10-20 (43 jobs).
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, join_location, parse_iso

FEED_URL = "https://maxonic.com/api/jobs.php"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class MaxonicScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="maxonic",
        company_name="Maxonic",
        careers_url="https://maxonic.com/jobs/",
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "Maxonic"
    IT_CATEGORY_KEYS = ("type",)

    async def fetch_raw(self) -> list:
        data = await self._http("GET", FEED_URL)
        return self.take_it(self.expect_list(data, "results"))

    def parse_job(self, raw: dict):
        if not isinstance(raw, dict) or not raw.get("id"):
            return None
        remote = str(raw.get("remote") or "").strip().lower()
        return self.make_job(
            title=raw.get("title"),
            location=join_location(raw.get("city"), raw.get("state")),
            job_url=raw.get("applyUrl") or "https://maxonic.com/jobs/",
            external_job_id=raw.get("id"),
            posted_date=parse_iso(raw.get("posted")),
            employment_type_raw=raw.get("type") or None,
            remote_type="remote" if remote in ("1", "yes", "true", "remote") else None,
        )
