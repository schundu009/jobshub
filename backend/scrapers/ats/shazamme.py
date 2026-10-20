"""
Shazamme job boards (staffing-firm sites built on Duda with Shazamme's job
widget, mostly fed from Bullhorn: DeWinter Group, Talent Groups, ...).

The widget on the firm's jobs page loads every live job of the site in one
call:

    GET https://shazamme.io/job-results/<siteID>?
    -> [{"data": {"jobID", "jobName", "city", "state", "workType", "salaryFrom", "jobURL", ...}}, ...]

Each job carries its own page on the firm's site (jobURL). A board is the
Shazamme siteID (a UUID; the widget's config holds it).
"""

import re
from typing import Optional

from contracts.scrapers._base import join_location, norm_period, parse_iso, simple_employment_type, to_float
from scrapers.ats import BoardType, register
from scrapers.base import ScrapedJob, ScrapeResult

_SITE_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_NONE = re.compile(r"^-?\s*none specified\s*-?$", re.I)


def results_url(board: str) -> str:
    return f"https://shazamme.io/job-results/{board}?"


def _value(raw: dict, key: str) -> str:
    value = str(raw.get(key) or "").strip()
    return "" if _NONE.match(value) else value


class ShazammeMixin:
    MAX_JOBS = 1500

    async def scrape(self) -> ScrapeResult:
        data = await self._request("GET", results_url(self.BOARD), lambda r: r.json(content_type=None))
        rows = [r.get("data") if isinstance(r, dict) and isinstance(r.get("data"), dict) else r
                for r in self.expect_list(data)]
        live = [r for r in rows if isinstance(r, dict) and str(r.get("activeStatus", True)).lower() != "false"]
        jobs = self.parse_all(live[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=len(live) <= self.MAX_JOBS)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        title = _value(raw, "jobName")
        url = _value(raw, "jobURL")
        job_id = _value(raw, "jobID")
        if not title or not url or not job_id:
            return None
        location = join_location(_value(raw, "city"), _value(raw, "state")) or _value(raw, "location") or _value(raw, "country")
        emp = _value(raw, "workType") or _value(raw, "jobType") or None
        pay_min = pay_max = period = None
        if str(raw.get("isDisplaySalary")).lower() == "true":
            pay_min, pay_max = to_float(raw.get("salaryFrom")), to_float(raw.get("salaryTo"))
            period = norm_period(_value(raw, "salaryType")) or norm_period(_value(raw, "salaryTypeGoogleSEO"))
            if not period or not (pay_min or pay_max):
                pay_min = pay_max = period = None
            else:
                pay_min, pay_max = pay_min or pay_max, pay_max or pay_min
        work_model = _value(raw, "workModel").lower()
        return ScrapedJob(
            title=title,
            location=location,
            job_url=url,
            external_job_id=job_id,
            job_description=self.clean_html(raw.get("fullDescription") or raw.get("shortDescription")),
            department=_value(raw, "category") or _value(raw, "industry") or None,
            posted_date=parse_iso(raw.get("addedOnUTC")) or parse_iso(raw.get("postedDate")),
            employment_type=simple_employment_type(emp),
            employment_type_raw=emp,
            remote_type=work_model if work_model in ("remote", "hybrid", "on-site", "onsite") else None,
            pay_rate_min=pay_min,
            pay_rate_max=pay_max,
            pay_period=period,
            salary_min=int(pay_min) if period == "year" and pay_min else None,
            salary_max=int(pay_max) if period == "year" and pay_max else None,
            extra={k: v for k, v in {"reference": _value(raw, "referenceNumber"), "salary_text": _value(raw, "salary"),
                                     "postal_code": _value(raw, "postalCode")}.items() if v},
        )


register(BoardType(
    name="shazamme",
    mixin=ShazammeMixin,
    valid=lambda board: bool(_SITE_ID.fullmatch(board or "")),
    start_url=results_url,
))
