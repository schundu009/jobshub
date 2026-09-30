"""
Motion Recruitment (tech jobs board).

Source: ``https://motionrecruitment.com/tech-jobs?start=N`` - the Next.js board is
server-rendered and its React Server Components payload
(``self.__next_f.push([1, "..."])`` chunks in the HTML) holds each posting as
JSON: id, title, address, dateAdded, employmentType (Contract / Contract to Hire
/ Direct Hire), payMin/payMax + isPayHourly, specialties, and a reference to the
description text chunk. 20 postings per page, newest first.
Recruiter ("owner") details are not stored.
Verified 2026-09-29 (~910 postings).
"""

import json
import re
from typing import Optional

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_country, join_location, parse_iso

LIST_URL = "https://motionrecruitment.com/tech-jobs"
PAGE_SIZE = 20
_PUSH_RE = re.compile(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)', re.S)
_JOB_START_RE = re.compile(r'\{"instance":"[a-z]+","isPublic"')
_TOTAL_RE = re.compile(r'"dataSet":\{"total":(\d+)')


def rsc_text(html: str) -> str:
    """Concatenate the RSC flight chunks embedded in a Next.js page."""
    out = []
    for chunk in _PUSH_RE.findall(html):
        try:
            out.append(json.loads(f'"{chunk}"'))
        except ValueError:
            continue
    return "".join(out)


def rsc_text_ref(flight: str, ref: str) -> Optional[str]:
    """Resolve a "$1c" reference to its "1c:T<hexlen>,<text>" row."""
    key = ref.lstrip("$")
    m = re.search(r"(?:^|\n)" + re.escape(key) + r":T([0-9a-f]+),", flight)
    if not m:
        return None
    n = int(m.group(1), 16)
    data = flight[m.end():].encode("utf-8")[:n]
    return data.decode("utf-8", errors="ignore")


def parse_motion_page(html: str) -> tuple[list[dict], Optional[int]]:
    flight = rsc_text(html)
    dec = json.JSONDecoder()
    jobs, seen = [], set()
    for m in _JOB_START_RE.finditer(flight):
        try:
            obj, _ = dec.raw_decode(flight, m.start())
        except ValueError:
            continue
        if not isinstance(obj, dict) or "id" not in obj or obj["id"] in seen:
            continue
        seen.add(obj["id"])
        desc = obj.get("description")
        if isinstance(desc, str) and desc.startswith("$"):
            obj["description"] = rsc_text_ref(flight, desc)
        jobs.append(obj)
    total = _TOTAL_RE.search(flight)
    return jobs, int(total.group(1)) if total else None


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class MotionRecruitmentScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="motionrecruitment",
        company_name="Motion Recruitment",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    AGENCY_NAME = "Motion Recruitment"

    async def fetch_raw(self) -> list:
        raw, start, seen = [], 0, set()
        while len(raw) < self.MAX_JOBS:
            html = await self._http("GET", LIST_URL, params={"start": str(start)} if start else None,
                                    expect="text")
            jobs, total = parse_motion_page(html)
            fresh = [j for j in jobs if j["id"] not in seen]
            seen.update(j["id"] for j in fresh)
            raw.extend(fresh)
            start += PAGE_SIZE
            if not fresh or (total and start >= total) or self.out_of_time():
                break
        return raw

    def parse_job(self, raw: dict):
        addr = raw.get("address") or {}
        country = addr.get("countryName") or addr.get("country")
        if country and not is_us_country(country):
            return None
        etype = raw.get("employmentType") or {}
        lo, hi = raw.get("payMin"), raw.get("payMax")
        period = ("hour" if raw.get("isPayHourly") else "year") if (lo or hi) else None
        skills = [s.get("name") for s in ((raw.get("specialties") or {}).get("data") or []) if isinstance(s, dict)]
        remote = (raw.get("remote") or "").lower()
        return self.make_job(
            title=raw.get("title"),
            location=join_location((addr.get("city") or "").title(), addr.get("state")),
            job_url=raw.get("url") or f"{LIST_URL}/job/{raw.get('id')}",
            external_job_id=raw.get("id"),
            description=raw.get("description"),
            posted_date=parse_iso(raw.get("dateAdded")),
            employment_type_raw=etype.get("originalName") or etype.get("name"),
            pay_min=lo, pay_max=hi, pay_period=period,
            department=((raw.get("categories") or {}).get("data") or [{}])[0].get("name"),
            remote_type={"remote": "remote", "hybrid": "hybrid", "onsite": "on-site",
                         "on-site": "on-site"}.get(remote),
            skills=skills,
        )
