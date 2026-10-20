"""
Vincere quick job boards / engagement hubs (<firm>.vincere.io boards on the
firm's own host: jobs.techire.ai, careers.edisonsmart.com, ...).

The board's search page is a Laravel app: the page carries a CSRF token
(<meta name="csrf-token">) and a session cookie, and its script posts the
search form to

    POST https://<host>/ajax/search-jobs   (multipart: unit, radius, page, search=1)
    -> {"items": [...], "total": N, "more": true}

ten jobs a page. We do the same: open the board's page once, then page
through the search with that token. A job's page is /job/<id>/<slug>. A board
is the board's host.
"""

import re
from typing import List, Optional

import aiohttp

from contracts.scrapers._base import join_location, norm_period, parse_iso, simple_employment_type, slugify, to_float
from scrapers.ats import BoardType, register
from scrapers.ats._jobtext import LOCATION_LABELS, html_text, label_value
from scrapers.base import ScrapedJob, ScrapeResult

_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
_PIN = re.compile(r"\U0001F4CD\s*([^\n.]{2,80})")  # "📍 San Francisco (on-site or hybrid)"
_CSRF = re.compile(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', re.I)
_LABELS = {"PERMANENT": "Permanent", "CONTRACT": "Contract", "TEMPORARY": "Temporary", "FULL_TIME": "Full-time",
           "PART_TIME": "Part-time", "TEMPORARY_TO_PERMANENT": "Temp to Perm", "INTERIM_PROJECT_CONSULTING": "Interim"}


def search_url(board: str) -> str:
    return f"https://{board}/ajax/search-jobs"


def _form(page: int) -> aiohttp.FormData:
    form = aiohttp.FormData()
    for key, value in (("unit", "mile"), ("radius", "100"), ("page", str(page)), ("search", "1")):
        form.add_field(key, value)
    return form


class VincereMixin:
    MAX_JOBS = 1000
    MAX_PAGES = 120

    async def scrape(self) -> ScrapeResult:
        page_html = await self._request("GET", f"https://{self.BOARD}/", lambda r: r.text())
        m = _CSRF.search(page_html or "")
        if not m:
            return ScrapeResult(success=False, error_message="Vincere board page has no csrf-token")
        headers = {"X-CSRF-TOKEN": m.group(1), "X-Requested-With": "XMLHttpRequest",
                   "Referer": f"https://{self.BOARD}/", "Accept": "application/json"}
        raw: List[dict] = []
        total = 0
        more = False
        for page in range(1, self.MAX_PAGES + 1):
            data = await self._request("POST", search_url(self.BOARD), lambda r: r.json(content_type=None),
                                       data=_form(page), headers=headers)
            rows = self.expect_list(data, "items")
            raw.extend(rows)
            total = int(data.get("total") or 0)
            more = bool(data.get("more"))
            if not rows or not more or len(raw) >= min(total or self.MAX_JOBS, self.MAX_JOBS):
                break
        jobs = self.parse_all(raw)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=len(raw) >= total and not more)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        title = (raw.get("job_title") or "").strip()
        job_id = str(raw.get("id") or "")
        if not title or not job_id:
            return None
        place = raw.get("location") if isinstance(raw.get("location"), dict) else {}
        location = (join_location(place.get("city"), place.get("state")) or (place.get("address") or "").strip()
                    or ((place.get("location_name") or "").strip() if len(place.get("location_name") or "") > 2 else "")
                    or (place.get("country") or "").strip())
        description = raw.get("public_description") or ""
        if not location:
            text = html_text(description)
            pin = _PIN.search(text)
            location = label_value(text, LOCATION_LABELS) or (pin.group(1).strip(" .,") if pin else "")
        job_type = _LABELS.get(str(raw.get("job_type") or "").upper(), raw.get("job_type"))
        time_type = _LABELS.get(str(raw.get("employment_type") or "").upper(), raw.get("employment_type"))
        emp = ", ".join(v for v in (job_type, time_type) if v) or None
        rate = to_float(raw.get("pay_rate"))
        lo, hi = to_float(raw.get("salary_from")), to_float(raw.get("salary_to"))
        period = norm_period(raw.get("salary_type"))
        if rate and str(raw.get("job_type") or "").upper() in ("CONTRACT", "TEMPORARY"):
            lo = hi = rate
            period = period if period and period != "year" else "hour"
        if not (lo or hi) or not period:
            lo = hi = period = None
        else:
            lo, hi = lo or hi, hi or lo
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"https://{self.BOARD}/job/{job_id}/{slugify(title) or 'job'}",
            external_job_id=job_id,
            job_description=self.clean_html(description),
            posted_date=parse_iso(raw.get("published_date") or raw.get("open_date")),
            employment_type=simple_employment_type(job_type),
            employment_type_raw=emp,
            pay_rate_min=lo,
            pay_rate_max=hi,
            pay_period=period,
            salary_min=int(lo) if period == "year" and lo else None,
            salary_max=int(hi) if period == "year" and hi else None,
            extra={"country": place.get("country")} if place.get("country") else {},
        )


register(BoardType(
    name="vincere",
    mixin=VincereMixin,
    valid=lambda board: bool(_HOST.fullmatch(board or "")),
    start_url=search_url,
    careers_url=lambda board: f"https://{board}/",
))
