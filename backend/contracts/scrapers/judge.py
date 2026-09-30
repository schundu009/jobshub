"""
The Judge Group - Information Technology and Engineering postings.

Endpoint: ``POST https://www.judge.com/wp-admin/admin-ajax.php?action=jdg_get_jobs``
- the call the judge.com/jobs/ board makes (robots.txt explicitly allows
admin-ajax.php). 20 postings per page, newest first; the body is a JSON string
holding JSON. Postings carry type ("Contract" / "Permanent") and a salary text
("$60.00 USD Hourly - $70.00 USD Hourly").
Public posting URL: https://www.judge.com/jobs/details/{jobOrderId}/.
IT only: the InformationTechnology and Engineering categories are requested and
each page is filtered per title with services.it_roles. Engineering is kept at
the API because it holds ~140 IT postings (embedded, firmware, test automation,
...; live check 2026-09-29: 822 IT with it vs 684 without); its mechanical /
civil / manufacturing postings are dropped by the title filter.
Verified 2026-09-29 (~750 IT + Engineering postings).
"""

import json

from scrapers.base import ScraperConfig, ScraperType, UnexpectedResponseError
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_state, parse_iso, parse_pay_text

API_URL = "https://www.judge.com/wp-admin/admin-ajax.php?action=jdg_get_jobs"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class JudgeScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="judge",
        company_name="The Judge Group",
        careers_url="https://www.judge.com/jobs/",
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "The Judge Group"
    CATEGORIES = ["InformationTechnology", "Engineering"]
    IT_CATEGORY_KEYS = ("category",)

    def _payload(self, page: int) -> dict:
        return {"payload": {
            "categories": self.CATEGORIES, "countries": "USA",
            "geo": [{"distance": "", "latLong": [0], "location": ""}],
            "query": "", "states": "", "type": ["Any"], "page": page, "remote": False,
        }}

    async def fetch_raw(self) -> list:
        raw, page, seen, listed = [], 0, set(), 0
        while len(raw) < self.MAX_JOBS:
            data = await self._http("POST", API_URL, json_body=self._payload(page))
            if isinstance(data, str):
                try:
                    data = json.loads(data)
                except ValueError as e:
                    raise UnexpectedResponseError(f"jdg_get_jobs returned non-JSON text: {e}")
            hits = self.expect_list(data, "hits")
            fresh = [h for h in hits if h.get("jobOrderId") not in seen]
            seen.update(h.get("jobOrderId") for h in fresh)
            raw.extend(self.take_it(fresh))
            listed += len(fresh)
            total = data.get("total") or 0
            if not fresh or listed >= total or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        location = (raw.get("location") or "").strip()
        state = location.rsplit(",", 1)[-1].strip() if "," in location else ""
        if state and not is_us_state(state) and "remote" not in location.lower():
            return None
        lo, hi, period = parse_pay_text(raw.get("salary"))
        category = raw.get("category")
        if isinstance(category, dict):
            category = category.get("description")
        job_id = raw.get("jobOrderId")
        return self.make_job(
            title=raw.get("title"),
            location=location,
            job_url=f"https://www.judge.com/jobs/details/{job_id}/",
            external_job_id=job_id,
            description=raw.get("description"),
            posted_date=parse_iso(raw.get("opened")),
            employment_type_raw=raw.get("type"),
            pay_min=lo, pay_max=hi, pay_period=period,
            department=category,
        )
