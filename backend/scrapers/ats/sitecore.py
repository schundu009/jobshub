"""
Job boards searched through Sitecore Search (Sitecore Discover), the hosted
search a Sitecore site's job board calls from the browser (Horizontal Talent,
fed from Bullhorn).

    POST https://discover.sitecorecloud.io/discover/v2/<customer id>
         Authorization: <the site's public search key, in its own JS bundle>
         {"widget": {"items": [{"rfk_id": "rfkid_jobs", "entity": "jobs", "sources": ["<source id>"],
                                "search": {"offset": 0, "limit": 100, "filter": ...}}]}}
    -> {"widgets": [{"total_item": N, "content": [{"title", "city", "state", "employmenttype",
                                                     "jobboardid", ...}]}]}

A board is "<site host>/<customer id>/<source id>/<search key>"; a job's page
is https://<site host>/job-board/<jobboardid>.
"""

import re
from typing import List, Optional

from contracts.scrapers._base import US_STATES, join_location, parse_iso, simple_employment_type
from scrapers.ats import BoardType, register
from scrapers.base import ScrapedJob, ScrapeResult

DISCOVER = "https://discover.sitecorecloud.io/discover/v2"
_BOARD = re.compile(r"((?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})/(\d{4,12})/(\d{3,12})/([0-9a-f\-]{20,80})")


def sitecore_parts(board: str):
    m = _BOARD.fullmatch((board or "").strip())
    return m.groups() if m else None


def search_url(board: str) -> str:
    host, customer, source, _ = sitecore_parts(board)
    return f"{DISCOVER}/{customer}#{host}/{source}"


def search_body(source: str, offset: int, limit: int) -> dict:
    filters = [{"type": "eq", "name": n, "value": v}
               for n, v in (("isopen", "true"), ("ispublic", "true"), ("isdeleted", "false"))]
    return {"context": {"page": {"uri": "/job-board"}},
            "widget": {"items": [{"rfk_id": "rfkid_jobs", "entity": "jobs", "sources": [source],
                                  "search": {"content": {}, "offset": offset, "limit": limit,
                                             "sort": {"value": [{"name": "job_date_sort"}]},
                                             "filter": {"type": "and", "filters": filters}}}]}}


class SitecoreSearchMixin:
    PAGE_SIZE = 100
    MAX_JOBS = 1500

    async def scrape(self) -> ScrapeResult:
        host, customer, source, key = sitecore_parts(self.BOARD)
        headers = {"Authorization": key, "Referer": f"https://{host}/", "Origin": f"https://{host}"}
        raw: List[dict] = []
        total = 0
        while len(raw) < self.MAX_JOBS:
            data = await self.fetch_json(f"{DISCOVER}/{customer}", method="POST",
                                         json_data=search_body(source, len(raw), self.PAGE_SIZE), headers=headers)
            widget = (self.expect_list(data, "widgets") or [{}])[0]
            rows = self.expect_list(widget, "content")
            raw.extend(rows)
            total = int(widget.get("total_item") or 0)
            if len(rows) < self.PAGE_SIZE or len(raw) >= total:
                break
        jobs = self.parse_all(raw)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        title = (raw.get("title") or "").strip()
        job_id = str(raw.get("jobboardid") or raw.get("bullhornidentifier") or "").strip()
        if not title or not job_id.isdigit():
            return None
        host = sitecore_parts(self.BOARD)[0]
        city, state = (raw.get("city") or "").strip(), (raw.get("state") or "").strip()
        # Statewide postings carry the state's name as the city ("California", "CA").
        statewide = US_STATES.get(state.upper(), "").lower() == city.lower()
        location = city if statewide else join_location(city, state)
        remote = str(raw.get("remotefilters") or "")
        if not location and "Remote" in remote:
            location = "Remote"
        emp = (raw.get("employmenttype") or "").strip() or None
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"https://{host}/job-board/{job_id}",
            external_job_id=job_id,
            job_description=self.clean_html(raw.get("description")),
            department=(raw.get("bullhorncategory") or "").strip() or None,
            posted_date=parse_iso(raw.get("lastpublisheddate")),
            employment_type=simple_employment_type(emp),
            employment_type_raw=emp,
            remote_type="remote" if "Remote" in remote else "hybrid" if "Hybrid" in remote else None,
            extra={k: v for k, v in {"industry": raw.get("industry"), "zip": raw.get("zip") if raw.get("zip") != "99999" else None,
                                     "country": raw.get("country")}.items() if v},
        )


register(BoardType(
    name="sitecore",
    mixin=SitecoreSearchMixin,
    valid=lambda board: sitecore_parts(board) is not None,
    start_url=search_url,
    careers_url=lambda board: f"https://{sitecore_parts(board)[0]}/job-board",
))
