"""
Staffing firms that list jobs on their OWN website (no hosted ATS board we already read).

``OwnSiteStaffingScraper`` is a StaffingScraper (IT-only filter, contract fields via
make_job, MAX_JOBS / time budget, polite per-host pacing) whose ``_http`` also
- checks robots.txt before every HTML page (services.robots, cached a day),
- can send a raw ``data`` body (form posts, text/plain JSON),
and which exposes ``listing_items(payload)``: the pure step from one listing response
to its raw postings, used by the offline tests.

``CeipalRecordsMixin`` parses the Ceipal-shaped job records that two firms' own sites
serve from their own endpoints (holistic-partners.com, api.aloissolutions.com).

HTML helpers (soup, text_of, abs_url, ...) are shared with scrapers/custom/_own_site.py.
"""

import asyncio
import hashlib
import re
from typing import Any, Optional

from scrapers.custom._own_site import RobotsDisallowed, clean_location, parse_when, text_of  # noqa: F401
from scrapers.base import ScrapeResult

from ._base import StaffingScraper, parse_pay_text, slugify


def stable_id(*parts: Any) -> str:
    """Short stable id for boards whose postings carry none (title + location)."""
    key = "|".join(slugify(str(p or "")) for p in parts)
    return hashlib.sha1(key.encode()).hexdigest()[:16]


class OwnSiteStaffingScraper(StaffingScraper):
    ROBOTS_FOR_HTML = True

    def listing_items(self, payload: Any) -> list:
        raise NotImplementedError

    async def _robots_ok(self, url: str) -> bool:
        from services import robots
        return await asyncio.to_thread(robots.allowed, url)

    async def _http(self, method: str, url: str, *, params: Optional[dict] = None, json_body: Any = None,
                    data: Any = None, headers: Optional[dict] = None, expect: str = "json") -> Any:
        if expect == "text" and self.ROBOTS_FOR_HTML and not await self._robots_ok(url):
            raise RobotsDisallowed(url)
        await self._pace(url)
        session = await self.get_session()
        kwargs: dict = {"params": params, "headers": headers or {}}
        if json_body is not None:
            kwargs["json"] = json_body
        if data is not None:
            kwargs["data"] = data
        async with session.request(method, url, **kwargs) as resp:
            resp.raise_for_status()
            if expect == "text":
                return await resp.text()
            return await resp.json(content_type=None)

    async def get_text(self, url: str, **kw) -> str:
        return await self._http("GET", url, expect="text", **kw)

    async def get_page_or_none(self, url: str, **kw) -> Optional[str]:
        import aiohttp
        try:
            return await self.get_text(url, **kw)
        except aiohttp.ClientResponseError as e:
            if e.status == 404:
                return None
            raise

    async def scrape(self) -> ScrapeResult:
        try:
            return await super().scrape()
        except RobotsDisallowed as e:
            return ScrapeResult(success=False, error_message=f"robots.txt disallows {e}")


class CeipalRecordsMixin:
    """Ceipal job records (position_title, city/state/country, pay_rates, employment_type,
    requisition_description, job_code, created, post_on_careerportal)."""

    IT_TITLE_KEYS = ("public_job_title", "position_title")
    IT_CATEGORY_KEYS = ("industry", "job_category")
    IT_SKILLS_KEYS = ("skills",)

    def ceipal_location(self, raw: dict) -> str:
        city, state, country = raw.get("city"), raw.get("state"), raw.get("country")
        if country in ("United States", "USA", "US"):
            country = None if (city or state) else "United States"
        location = clean_location(city, state, country)
        if str(raw.get("remote_opportunities") or "").lower() == "yes":
            location = f"{location} (Remote)" if location else "Remote"
        return location

    def ceipal_pay(self, raw: dict) -> tuple:
        for rate in raw.get("pay_rates") or []:
            if not isinstance(rate, dict):
                continue
            hi = rate.get("max_pay_rate") or rate.get("pay_rate")
            lo = rate.get("min_pay_rate") or hi
            period = rate.get("pay_rate_pay_frequency_type")
            if hi and str(hi).replace(".", "", 1).isdigit() and period:
                return lo, hi, period
            lo2, hi2, per2 = parse_pay_text(f"{rate.get('pay_rate')} {period or ''}")
            if lo2:
                return lo2, hi2, per2
        return None, None, None

    def ceipal_job(self, raw: dict, job_url: str):
        lo, hi, period = self.ceipal_pay(raw)
        skills = raw.get("skills")
        if isinstance(skills, str):
            skills = [s.strip() for s in re.split(r"[,;|]", skills) if s.strip()]
        return self.make_job(
            title=raw.get("public_job_title") or raw.get("position_title"),
            location=self.ceipal_location(raw),
            job_url=job_url,
            external_job_id=raw.get("job_code") or raw.get("id"),
            description=raw.get("public_job_desc") or raw.get("requisition_description"),
            posted_date=parse_when(raw.get("created") or raw.get("job_start_date")),
            employment_type_raw=raw.get("employment_type"),
            pay_min=lo, pay_max=hi, pay_period=period,
            department=raw.get("industry") or raw.get("job_category") or None,
            remote_type="remote" if str(raw.get("remote_opportunities") or "").lower() == "yes" else None,
            skills=skills or None,
            extra={"tax_terms": raw.get("tax_terms")} if raw.get("tax_terms") else None,
        )
