"""
Jobot - consulting (contract) postings only.

Endpoint: ``POST https://jobot-com-api.jobot.net/rest/jobs/search`` - the call the
jobot.com/search page makes. ``positionType: "consulting"`` is Jobot's contract
bucket (the rest of the board is direct-hire "permanent"); ``size``/``from`` page
through it. jobot.com's robots.txt disallows crawling /jobs/*, which is not
fetched (the API host is separate; the /details/ URL is only linked).
Recruiter details in the response are not stored.
Verified 2026-09-29 (~350 consulting postings).
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_country, join_location, parse_iso

API_URL = "https://jobot-com-api.jobot.net/rest/jobs/search"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class JobotScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="jobot",
        company_name="Jobot",
        careers_url="https://jobot.com/search",
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "Jobot"
    PAGE_SIZE = 100
    POSITION_TYPE = "consulting"

    async def fetch_raw(self) -> list:
        raw, offset, seen = [], 0, set()
        while len(raw) < self.MAX_JOBS:
            body = {"location": "USA or REMOTE", "positionType": self.POSITION_TYPE,
                    "size": self.PAGE_SIZE, "from": offset}
            data = await self._http("POST", API_URL, json_body=body)
            docs = self.expect_list(data, "documents")
            fresh = [d for d in docs if d.get("id") not in seen]
            seen.update(d.get("id") for d in fresh)
            raw.extend(fresh)
            total = (((data.get("hits") or {}).get("total")) or {}).get("value") or 0
            offset += len(docs)
            if not fresh or offset >= total or self.out_of_time():
                break
        return raw

    def parse_job(self, raw: dict):
        loc = raw.get("primaryLocation") or {}
        addr = loc.get("postalAddress") or {}
        if addr.get("addressCountry") and not is_us_country(addr.get("addressCountry")):
            return None
        remote = bool(raw.get("isRemote"))
        location = join_location(addr.get("addressLocality"), addr.get("addressRegion")) or loc.get("address")
        comp_type = (raw.get("compensationType") or "").lower()
        lo, hi = raw.get("compensationMin"), raw.get("compensationMax")
        period = comp_type or None
        if not period and lo:
            period = "hour" if float(lo) < 500 else "year"
        descriptions = raw.get("descriptions") or []
        description = "\n\n".join(
            d.get("content") or d.get("text") or "" for d in descriptions if isinstance(d, dict)
        ).strip() or raw.get("header")
        skills = [s.get("name") if isinstance(s, dict) else s for s in (raw.get("skills") or [])]
        return self.make_job(
            title=raw.get("title"),
            location=location or ("Remote" if remote else ""),
            job_url=raw.get("detailsUrl") or f"https://jobot.com/details/{raw.get('slug')}/{raw.get('id')}",
            external_job_id=raw.get("id"),
            description=description,
            posted_date=parse_iso(raw.get("created")),
            employment_type_raw=raw.get("positionType"),
            pay_min=lo, pay_max=hi, pay_period=period,
            remote_type="remote" if remote else None,
            skills=skills,
        )
