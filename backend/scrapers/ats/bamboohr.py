"""
BambooHR career sites as job_boards rows (ats "bamboohr").

Board: the subdomain of <board>.bamboohr.com/careers, e.g. "wavelynx".
GET <board>.bamboohr.com/careers/list -> {"meta": {"totalCount"}, "result":
[{id, jobOpeningName, departmentLabel, employmentStatusLabel, location{city,
state}, atsLocation{...}, isRemote, locationType}]}. Each opening's
description is at /careers/<id>/detail ({"result": {"jobOpening":
{description, datePosted, ...}}}); boards are small, so those are read too
(up to DETAIL_LIMIT). A job opens at <board>.bamboohr.com/careers/<id>.
"""
import asyncio
import re
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import join_place
from scrapers.base import ScrapedJob, ScrapeResult

_SUB = re.compile(r"[a-z0-9][a-z0-9\-]{0,62}")
_LOCATION_TYPES = {"0": "on-site", "1": "remote", "2": "hybrid"}


class BambooHRMixin:
    DETAIL_LIMIT = 150

    async def _detail(self, job_id: str) -> dict:
        try:
            data = await self.fetch_json(f"https://{self.BOARD}.bamboohr.com/careers/{job_id}/detail")
            return ((data or {}).get("result") or {}).get("jobOpening") or {}
        except Exception as e:
            self.logger.info(f"BambooHR detail {job_id} skipped: {e}")
            return {}

    async def scrape(self) -> ScrapeResult:
        rows = self.expect_list(await self.fetch_json(self.API_URL), "result")
        if len(rows) <= self.DETAIL_LIMIT:
            sem = asyncio.Semaphore(4)

            async def one(row):
                async with sem:
                    row["_detail"] = await self._detail(row.get("id"))
            await asyncio.gather(*(one(r) for r in rows if r.get("id")))
        jobs = self.parse_all(rows)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=True)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id, title = raw.get("id"), (raw.get("jobOpeningName") or "").strip()
        if not job_id or not title:
            return None
        detail = raw.get("_detail") or {}
        loc = detail.get("location") or raw.get("location") or {}
        ats = raw.get("atsLocation") or {}
        location = join_place(loc.get("city") or ats.get("city"), loc.get("state") or ats.get("state") or ats.get("province"),
                              loc.get("addressCountry") or ats.get("country"))
        remote = "remote" if raw.get("isRemote") else _LOCATION_TYPES.get(str(raw.get("locationType")))
        if remote == "remote" and not location:
            location = "Remote"
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"https://{self.BOARD}.bamboohr.com/careers/{job_id}",
            external_job_id=str(job_id),
            job_description=detail.get("description") or None,
            department=raw.get("departmentLabel") or None,
            posted_date=self.parse_date(detail.get("datePosted")),
            remote_type=remote,
            employment_type_raw=raw.get("employmentStatusLabel") or None,
        )


register(BoardType(
    name="bamboohr",
    mixin=BambooHRMixin,
    valid=lambda board: bool(_SUB.fullmatch(board or "")),
    start_url=lambda board: f"https://{board}.bamboohr.com/careers/list",
    careers_url=lambda board: f"https://{board}.bamboohr.com/careers",
))
