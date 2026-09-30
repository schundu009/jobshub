"""
Robert Half (Technology practice, "RHT").

Endpoint: ``POST https://www.roberthalf.com/bin/jobSearchServlet`` - the call the
roberthalf.com/us/en/jobs search page makes (payload from its React bundle),
filtered to line of business RHT (Robert Half Technology), newest first,
100 per page. Postings carry structured job type (Temp / Temp to Perm / Perm)
and pay (payrate_min/max + payrate_period). Verified 2026-09-29 (~900 US jobs).
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, join_location, parse_iso

API_URL = "https://www.roberthalf.com/bin/jobSearchServlet"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class RobertHalfScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="roberthalf",
        company_name="Robert Half",
        careers_url="https://www.roberthalf.com/us/en/jobs",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    AGENCY_NAME = "Robert Half"
    LINES_OF_BUSINESS = ["RHT"]
    PAGE_SIZE = 100
    IT_AMBIGUOUS_DEFAULT = True  # already Robert Half Technology
    IT_CATEGORY_KEYS = ("functional_role",)
    IT_SKILLS_KEYS = ("skills",)

    def _payload(self, page: int) -> dict:
        return {
            "country": "us", "keywords": "", "location": "", "distance": "50",
            "remote": "Any", "remoteText": "", "languagecodes": [], "source": ["Salesforce"],
            "city": "", "emptype": "", "lobid": self.LINES_OF_BUSINESS, "jobtype": "",
            "postedwithin": "0", "timetype": "", "pagesize": self.PAGE_SIZE, "pagenumber": page,
            "mode": "", "payrate_min": 0, "payrate_period": "", "includedoe": "",
            "sortby": "PUBLISHED_DATE_DESC",
        }

    async def fetch_raw(self) -> list:
        raw, page, listed = [], 1, 0
        while len(raw) < self.MAX_JOBS:
            data = await self._http("POST", API_URL, json_body=self._payload(page))
            jobs = self.expect_list(data, "jobs")
            raw.extend(self.take_it(jobs))
            listed += len(jobs)
            total = int(str(data.get("found") or 0) or 0)
            if not jobs or listed >= total or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        if (raw.get("country") or "US").upper() != "US":
            return None
        description = "\n".join(p for p in (raw.get("description"), raw.get("skills")) if p)
        remote = (raw.get("remote") or "").lower()
        return self.make_job(
            title=raw.get("jobtitle"),
            location=join_location(raw.get("city"), raw.get("stateprovince")),
            job_url=raw.get("job_detail_url"),
            external_job_id=raw.get("unique_job_number"),
            description=description,
            posted_date=parse_iso(raw.get("date_posted")),
            employment_type_raw=raw.get("emptype"),
            pay_min=raw.get("payrate_min"),
            pay_max=raw.get("payrate_max"),
            pay_period=raw.get("payrate_period"),
            department=raw.get("functional_role"),
            remote_type="remote" if remote == "yes" else None,
            extra={"line_of_business": raw.get("lob_code")},
        )
