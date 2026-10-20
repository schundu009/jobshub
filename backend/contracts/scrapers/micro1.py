"""
micro1 - www.micro1.ai/experts/opportunities (AI talent network; own JSON API).

The opportunities page posts {"action": "get_all_jobs", "filters": {"type": ["EXPERT"]}}
to https://prod-api.micro1.ai/api/v1/job/portal?page=N&limit=50 (total ~250, newest
first; hourly rates, skills, domain). Posting page: https://jobs.micro1.ai/post/<job_id>.
Many roles are non-IT expert gigs (medicine, law, photography); IT only keeps the
technology ones. Verified 2026-10-20.
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, parse_iso
from ._own_site import OwnSiteStaffingScraper

API_URL = "https://prod-api.micro1.ai/api/v1/job/portal"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class Micro1Scraper(OwnSiteStaffingScraper):
    config = ScraperConfig(
        company_slug="micro1",
        company_name="micro1",
        careers_url="https://www.micro1.ai/experts/opportunities",
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "micro1"
    LIMIT = 50
    IT_TITLE_KEYS = ("job_name",)
    IT_CATEGORY_KEYS = ("domain_slug",)
    IT_SKILLS_KEYS = ("skills",)

    def listing_items(self, payload):
        return self.expect_list(payload, "data")

    async def fetch_raw(self) -> list:
        raw, page, seen = [], 1, 0
        while len(raw) < self.MAX_JOBS:
            data = await self._http("POST", API_URL, params={"page": page, "limit": self.LIMIT, "keyword": ""},
                                    json_body={"action": "get_all_jobs", "filters": {"type": ["EXPERT"]}},
                                    headers={"Origin": "https://www.micro1.ai"})
            jobs = self.listing_items(data)
            seen += len(jobs)
            raw.extend(self.take_it(jobs))
            if not jobs or seen >= int(data.get("total") or 0) or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        hourly = raw.get("ideal_hourly_rate") or {}
        lo, hi, period = hourly.get("min"), hourly.get("max"), "hour" if hourly else None
        if not hourly and isinstance(raw.get("ideal_yearly_compensation"), dict):
            y = raw["ideal_yearly_compensation"]
            lo, hi, period = y.get("min"), y.get("max"), "year"
        return self.make_job(
            title=raw.get("job_name"),
            location="Remote",
            job_url=f"https://jobs.micro1.ai/post/{raw.get('job_id')}",
            external_job_id=raw.get("job_id"),
            posted_date=parse_iso(raw.get("date_posted")),
            employment_type_raw=raw.get("engagement_type") or "Contract",
            pay_min=lo, pay_max=hi, pay_period=period,
            department=raw.get("domain_slug"),
            remote_type="remote",
            skills=raw.get("skills"),
        )
