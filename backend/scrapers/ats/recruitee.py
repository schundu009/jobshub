"""
Recruitee career sites as job_boards rows (ats "recruitee").

Board: the subdomain of <board>.recruitee.com, e.g. "infoprolearning".
GET <board>.recruitee.com/api/offers/ lists every published offer with its
description: {"offers": [{id, title, careers_url, location, city,
country, department, description, requirements, published_at, remote,
hybrid, on_site, employment_type_code, salary{min, max, period}}]}.
"""
import re
from datetime import datetime
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.base import ScrapedJob, ScrapeResult

_SUB = re.compile(r"[a-z0-9][a-z0-9\-]{0,62}")


class RecruiteeMixin:
    async def scrape(self) -> ScrapeResult:
        offers = self.expect_list(await self.fetch_json(self.API_URL), "offers")
        jobs = self.parse_all([o for o in offers if o.get("status", "published") == "published"])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=True)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id, title = raw.get("id"), (raw.get("title") or "").strip()
        if not job_id or not title:
            return None
        body = "\n".join(p for p in (raw.get("description"), raw.get("requirements")) if p) or None
        posted = None
        try:
            posted = datetime.strptime((raw.get("published_at") or "")[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            posted = None
        remote = "remote" if raw.get("remote") else "hybrid" if raw.get("hybrid") else "on-site" if raw.get("on_site") else None
        salary = raw.get("salary") or {}

        def num(v):
            try:
                return float(v) or None
            except (TypeError, ValueError):
                return None
        period = str(salary.get("period") or "").lower() or None
        location = " ".join((raw.get("location") or "").split()).replace(" ,", ",")
        return ScrapedJob(
            title=title,
            location=location,
            job_url=raw.get("careers_url") or f"https://{self.BOARD}.recruitee.com/o/{raw.get('slug')}",
            external_job_id=str(job_id),
            job_description=body,
            department=raw.get("department") or None,
            posted_date=posted,
            remote_type=remote,
            employment_type_raw=raw.get("employment_type_code") or None,
            pay_rate_min=num(salary.get("min")), pay_rate_max=num(salary.get("max")),
            pay_period=period if period in ("hour", "day", "week", "month", "year") else None,
        )


register(BoardType(
    name="recruitee",
    mixin=RecruiteeMixin,
    valid=lambda board: bool(_SUB.fullmatch(board or "")),
    start_url=lambda board: f"https://{board}.recruitee.com/api/offers/",
    careers_url=lambda board: f"https://{board}.recruitee.com/",
))
