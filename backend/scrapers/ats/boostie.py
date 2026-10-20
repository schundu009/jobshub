"""
Boostie job boards as job_boards rows (ats "boostie").

Board: the board's domain, e.g. "jobs.theashgroup.com". The board app asks
auth.boostie.com/api/boardClients/getByBoardDomain?boardDomain=<board> for
the client (externalId, apiUrl), then POSTs <apiUrl>api/boardJobPages/search
(header X-Client-ExternalId) with its table search, paged by currentPage /
resultsPerPage: {"data": {"count", "items": [{id, atsId, jobTitle,
jobSummaryShort, employmentType, location, jobPageUrl ("/job/<slug>")}]}}.
"""
import re
from typing import Optional
from urllib.parse import urljoin

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import HOST, remote_from
from scrapers.base import ScrapedJob, ScrapeResult, UnexpectedResponseError

CLIENT_URL = "https://auth.boostie.com/api/boardClients/getByBoardDomain"


class BoostieMixin:
    PAGE_SIZE = 100
    MAX_JOBS = 1500

    def _search(self, page: int) -> dict:
        return {"searchText": None, "currentPage": page, "resultsPerPage": self.PAGE_SIZE,
                "sortProperty": None, "sortOrder": None, "categoryIds": [], "specialtyIds": [],
                "employmentTypes": [], "shifts": [], "states": [], "cities": [], "isRemote": False,
                "skip": (page - 1) * self.PAGE_SIZE}

    async def scrape(self) -> ScrapeResult:
        client = ((await self.fetch_json(CLIENT_URL, params={"boardDomain": self.BOARD})) or {}).get("data") or {}
        api, ext = (client.get("apiUrl") or ""), client.get("externalId")
        if not ext or not re.fullmatch(r"https://[a-z0-9\-]+\.boostie\.com/", api):
            raise UnexpectedResponseError("Boostie has no client for this board domain")
        headers = {"X-Client-ExternalId": ext, "Origin": f"https://{self.BOARD}"}
        raw, total, page = [], None, 1
        while len(raw) < self.MAX_JOBS:
            data = await self.fetch_json(f"{api}api/boardJobPages/search", method="POST",
                                         json_data=self._search(page), headers=headers)
            body = (data or {}).get("data") or {}
            items = self.expect_list(body, "items")
            total = int(body.get("count") or 0)
            raw.extend(items)
            if not items or len(raw) >= total:
                break
            page += 1
        jobs = self.parse_all([r for r in raw if r.get("isPublished", True) and r.get("isOpen", True)][: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=page,
                            complete=total is not None and len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        title, path = (raw.get("jobTitle") or "").strip(), raw.get("jobPageUrl")
        if not title or not path or not raw.get("id"):
            return None
        location = raw.get("location") or ""
        return ScrapedJob(
            title=title,
            location=location,
            job_url=urljoin(f"https://{self.BOARD}/", path),
            external_job_id=str(raw.get("atsId") or raw["id"]),
            remote_type=remote_from(location),
            employment_type_raw=raw.get("employmentType") or None,
            extra={"summary": raw.get("jobSummaryShort")},
        )


register(BoardType(
    name="boostie",
    mixin=BoostieMixin,
    valid=lambda board: bool(HOST.fullmatch(board or "")),
    start_url=lambda board: f"{CLIENT_URL}?boardDomain={board}",
    careers_url=lambda board: f"https://{board}/",
))
