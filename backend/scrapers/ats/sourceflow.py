"""
SourceFlow recruitment sites (UK/US agency sites built on SourceFlow, mostly
fed from Bullhorn or Vincere).

The site's own search page posts to its own JSON API:

    POST https://<site>/_sf/api/v1/jobs/search.json
         {"job_search": {"query": "", "location": {}, "filters": {}, "offset": 0, "jobs_per_page": 50}}
    -> {"total_size": N, "results": [{"job": {...}}, ...]}

The API answers at most 50 a page. A job's page is /<prefix>/<url_slug>/,
where the prefix is the site's own ("jobs" on most, "search-jobs" on some),
so a board is "<host>/<prefix>", e.g. "www.risetechnical.com/search-jobs".
"""

import re
from datetime import datetime, timezone
from typing import List, Optional

from contracts.scrapers._base import join_location, parse_pay_text, simple_employment_type, to_float
from scrapers.ats import BoardType, register
from scrapers.ats._jobtext import LOCATION_LABELS, html_text, label_value
from scrapers.base import ScrapedJob, ScrapeResult

_BOARD = re.compile(r"((?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})/([A-Za-z0-9_\-/]{1,60})")
_TYPE_CATEGORIES = ("employment type", "job type", "contract type", "type", "position type")


def sourceflow_parts(board: str) -> Optional[tuple[str, str]]:
    m = _BOARD.fullmatch((board or "").strip().rstrip("/"))
    return (m.group(1), m.group(2).strip("/")) if m else None


def search_url(board: str) -> str:
    return f"https://{sourceflow_parts(board)[0]}/_sf/api/v1/jobs/search.json"


def search_body(offset: int, per_page: int) -> dict:
    return {"job_search": {"query": "", "location": {}, "filters": {}, "offset": offset, "jobs_per_page": per_page}}


def _epoch(value) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc).replace(tzinfo=None) if value else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


class SourceFlowMixin:
    PAGE_SIZE = 50
    MAX_JOBS = 1500

    async def scrape(self) -> ScrapeResult:
        raw: List[dict] = []
        total = 0
        while len(raw) < self.MAX_JOBS:
            data = await self.fetch_json(search_url(self.BOARD), method="POST",
                                         json_data=search_body(len(raw), self.PAGE_SIZE))
            rows = self.expect_list(data, "results")
            raw.extend(r.get("job") or {} for r in rows if isinstance(r, dict))
            total = int(data.get("total_size") or 0)
            if len(rows) < self.PAGE_SIZE or len(raw) >= total:
                break
        jobs = self.parse_all(raw)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        title = (raw.get("title") or "").strip()
        slug = (raw.get("url_slug") or "").strip()
        job_id = str(raw.get("id") or "")
        if not title or not slug or not job_id:
            return None
        host, prefix = sourceflow_parts(self.BOARD)
        location = (raw.get("original_location") or "").strip() or "; ".join(a for a in raw.get("addresses") or [] if a)
        if not location:
            for loc in (raw.get("derived_info") or {}).get("locations") or []:
                address = loc.get("postal_address") or {}
                location = join_location(address.get("locality"), address.get("administrative_area"), address.get("region_code"))
                if location:
                    break
        if not location:
            for category in raw.get("categories") or []:
                if "location" in str(category.get("name") or "").lower():
                    values = [v.get("name") for v in category.get("values") or [] if v.get("name")]
                    if any(str(v).lower() == "remote" for v in values):
                        location = "Remote"
        if not location:
            location = label_value(html_text(raw.get("description")), LOCATION_LABELS) or ""
        emp = None
        for category in raw.get("categories") or []:
            if str(category.get("name") or "").strip().lower() in _TYPE_CATEGORIES:
                emp = ", ".join(v.get("name") for v in category.get("values") or [] if v.get("name")) or None
                break
        package = (raw.get("salary_package") or "").strip()
        pay_min, pay_max, period = parse_pay_text(package)
        low, high = to_float(raw.get("salary_low")), to_float(raw.get("salary_high"))
        if not pay_min and (low or high):
            pay_min, pay_max = low or high, high or low
            period = period or ("year" if (pay_min or 0) >= 1000 else None)
            if not period:
                pay_min = pay_max = None
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"https://{host}/{prefix}/{slug}/",
            external_job_id=job_id,
            job_description=self.clean_html(raw.get("description")),
            posted_date=_epoch(raw.get("published_at") or raw.get("created_at")),
            employment_type=simple_employment_type(emp),
            employment_type_raw=emp,
            pay_rate_min=pay_min,
            pay_rate_max=pay_max,
            pay_period=period,
            salary_min=int(pay_min) if period == "year" and pay_min else None,
            salary_max=int(pay_max) if period == "year" and pay_max else None,
            extra={k: v for k, v in {"salary_text": package or None, "reference": raw.get("external_reference"),
                                     "consultant": raw.get("consultant_name")}.items() if v},
        )


register(BoardType(
    name="sourceflow",
    mixin=SourceFlowMixin,
    valid=lambda board: sourceflow_parts(board) is not None,
    start_url=search_url,
    careers_url=lambda board: "https://{}/{}/".format(*sourceflow_parts(board)),
))
