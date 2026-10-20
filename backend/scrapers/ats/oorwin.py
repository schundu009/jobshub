"""
Oorwin career portals as job_boards rows (ats "oorwin").

Board: the portal subdomain of <board>.oorwin.com/careers, e.g.
"themesoftinc". The portal lists jobs with POST
api.oorwin.ai/api/v2/careers/getJobList {"sub_domain", "page", "limit",
"list_type": 1, ...} -> {"data": {"list_details": {"total", "last_page",
"data": [{id, title, code, city, state_format_name, country_format_name,
remote_status, job_type, cp_published_on, computed_sha1_job_id}]}}}.
A job opens at <board>.oorwin.com/careers/index.html#/job/<computed_sha1_job_id>
(the link the portal's own share button builds).
"""
import re
from datetime import datetime
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import join_place, remote_from
from scrapers.base import ScrapedJob, ScrapeResult

LIST_URL = "https://api.oorwin.ai/api/v2/careers/getJobList"
_SUB = re.compile(r"[a-z0-9][a-z0-9\-]{0,62}")


class OorwinMixin:
    PAGE_SIZE = 100
    MAX_PAGES = 15

    async def scrape(self) -> ScrapeResult:
        raw, total, page, last = [], None, 1, 1
        while page <= self.MAX_PAGES:
            data = await self.fetch_json(LIST_URL, method="POST", json_data={
                "limit": self.PAGE_SIZE, "page": page, "order": "cp_published_on", "sort": "desc",
                "list_type": 1, "sub_domain": self.BOARD, "getDefaultData": page == 1, "template_format": 2})
            details = ((data or {}).get("data") or {}).get("list_details") or {}
            rows = self.expect_list(details, "data")
            total, last = int(details.get("total") or 0), int(details.get("last_page") or 1)
            raw.extend(rows)
            if not rows or page >= last:
                break
            page += 1
        jobs = self.parse_all(raw)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=page,
                            complete=total is not None and len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id, title, sha = raw.get("id"), (raw.get("title") or "").strip(), raw.get("computed_sha1_job_id")
        if not job_id or not title or not sha:
            return None
        city = (raw.get("city") or "").strip()
        location = join_place(city.title() if city.isupper() else city, raw.get("state_format_name"),
                              raw.get("country_format_name"))
        posted = None
        try:
            posted = datetime.strptime((raw.get("cp_published_on") or "")[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            posted = None
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"https://{self.BOARD}.oorwin.com/careers/index.html#/job/{sha}",
            external_job_id=str(job_id),
            posted_date=posted,
            remote_type=remote_from(raw.get("remote_status")),
            employment_type_raw=raw.get("job_type") or raw.get("placement_type") or None,
            extra={"code": raw.get("code")},
        )


register(BoardType(
    name="oorwin",
    mixin=OorwinMixin,
    valid=lambda board: bool(_SUB.fullmatch(board or "")),
    start_url=lambda board: f"{LIST_URL}?sub_domain={board}",
    careers_url=lambda board: f"https://{board}.oorwin.com/careers/index.html#/list",
))
