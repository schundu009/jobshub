"""
PeopleStrong candidate portals as job_boards rows (ats "peoplestrong").

Board: the portal host, e.g. "larsentoubrocareers.peoplestrong.com". The
portal's job list is POST <host>/api/cp/rest/altone/cp/jobs/v1?offset=N&limit=M
with an empty filter ({}) -> {"totalRecords", "response": [{requisitionId,
jobTitle, jobCode, jobDetailUrl, jobPostedDate, locationHierarchyComplete
("India>Gujarat>Ahmedabad"), organizationUnit, expRange, skills, ...}]};
it serves at most 99 a page.
"""
import asyncio
import re
from datetime import datetime
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.base import ScrapedJob, ScrapeResult

_HOST = re.compile(r"[a-z0-9][a-z0-9\-]{0,62}\.peoplestrong\.com")


class PeopleStrongMixin:
    PAGE_SIZE = 99
    MAX_JOBS = 1500
    TIME_BUDGET_SECONDS = 50

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS
        raw, seen, total, offset = [], set(), None, 0
        while len(raw) < self.MAX_JOBS and loop.time() < deadline:
            data = await self.fetch_json(f"{self.API_URL}?offset={offset}&limit={self.PAGE_SIZE}",
                                         method="POST", json_data={})
            rows = self.expect_list(data, "response") if offset == 0 else (data or {}).get("response") or []
            total = int((data or {}).get("totalRecords") or 0)
            fresh = [r for r in rows if r.get("requisitionId") not in seen]
            seen.update(r.get("requisitionId") for r in fresh)
            raw.extend(fresh)
            if not fresh or len(raw) >= total:
                break
            offset += len(rows)
        jobs = self.parse_all(raw[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs),
                            complete=total is not None and len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        req, title = raw.get("requisitionId"), (raw.get("jobTitle") or "").strip()
        if not req or not title:
            return None
        hierarchy = [p.strip() for p in (raw.get("locationHierarchyComplete") or "").split(">") if p.strip()]
        location = ", ".join(reversed(hierarchy)) or raw.get("locationHierarchy") or ""
        code = (raw.get("jobCode") or "").replace("/", "_")
        skills = raw.get("skills") or {}
        return ScrapedJob(
            title=title,
            location=location,
            job_url=raw.get("jobDetailUrl") or f"https://{self.BOARD}/job/detail/{code}",
            external_job_id=str(req),
            department=raw.get("organizationUnit") or raw.get("roleType") or None,
            posted_date=self.parse_date(raw.get("jobPostedDate")),
            extra={"job_code": raw.get("jobCode"), "experience": raw.get("expRange"),
                   "skills": (skills.get("mustTohave") or []) + (skills.get("goodtohave") or [])},
        )


register(BoardType(
    name="peoplestrong",
    mixin=PeopleStrongMixin,
    valid=lambda board: bool(_HOST.fullmatch(board or "")),
    start_url=lambda board: f"https://{board}/api/cp/rest/altone/cp/jobs/v1",
    careers_url=lambda board: f"https://{board}/job/joblist",
))
