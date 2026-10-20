"""
SGA, Inc. (Software Guidance & Assistance) job search, www.sgainc.com/job-search.

The page loads its open roles from the site's own job service:

    GET https://www.sgainc.com/api/jobsvc/v1/jobs/recent-open-roles
    -> {"top_results": [{"id", "reference", "title", "city", "state", "payrate_min",
                         "payrate_max", "payrate_per", "remote_pct", ...}], ...}

and links each role as /job-search/<reference>. A board is the site's host.
"""

import re
from typing import Optional

from contracts.scrapers._base import join_location, norm_period, parse_iso, to_float
from scrapers.ats import BoardType, register
from scrapers.base import ScrapedJob, ScrapeResult

_HOSTS = {"www.sgainc.com"}


def roles_url(board: str) -> str:
    return f"https://{board}/api/jobsvc/v1/jobs/recent-open-roles"


class SgaJobsMixin:
    async def scrape(self) -> ScrapeResult:
        data = await self.fetch_json(roles_url(self.BOARD))
        rows = self.expect_list(data, "top_results")
        jobs = self.parse_all(rows)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=True)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        title = (raw.get("title") or "").strip()
        ref = str(raw.get("reference") or "").strip()
        if not title or not re.fullmatch(r"[A-Za-z0-9\-]{2,40}", ref):
            return None
        remote = raw.get("remote_pct")
        location = join_location(raw.get("city"), raw.get("state"))
        if not location and remote == 100:
            location = "Remote"
        lo, hi = to_float(raw.get("payrate_min")), to_float(raw.get("payrate_max"))
        period = norm_period(raw.get("payrate_per")) if (lo or hi) else None
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"https://{self.BOARD}/job-search/{ref}",
            external_job_id=str(raw.get("id") or ref),
            job_description=(raw.get("summary") or "").strip() or None,
            department=raw.get("industry") or None,
            posted_date=parse_iso(raw.get("last_updated")),
            remote_type="remote" if remote == 100 else "hybrid" if isinstance(remote, (int, float)) and remote > 0 else None,
            pay_rate_min=(lo or hi) if period else None,
            pay_rate_max=(hi or lo) if period else None,
            pay_period=period,
            extra={k: v for k, v in {"reference": ref, "remote_pct": remote}.items() if v is not None},
        )


register(BoardType(
    name="sgainc",
    mixin=SgaJobsMixin,
    valid=lambda board: board in _HOSTS,
    start_url=roles_url,
    careers_url=lambda board: f"https://{board}/job-search",
))
