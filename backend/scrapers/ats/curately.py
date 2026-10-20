"""
Curately career sites as job_boards rows (ats "curately").

Board: the career site's host, e.g. "careers.askconsulting.com". The site
pages its job cards from /api/v1/jobs/list?pageCount=N (N from 1; 20 cards a
page, "empty_List" past the end). Each card carries data-job-id,
data-job-title, data-job-location, data-job-workType, data-job-type,
data-job-payrateMin/Max, data-job-type-category-value and
data-job-applyLink, the posting's page on careers.curately.ai. Descriptions
are only in the per-job getJobInfo call and are left to the backfill.
"""
import asyncio
import re
from typing import Optional
from urllib.parse import quote

from bs4 import BeautifulSoup

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import HOST, remote_from
from scrapers.base import ScrapedJob, ScrapeResult


def curately_cards(html: str) -> list:
    soup = BeautifulSoup(html or "", "html.parser")
    rows: dict = {}
    keys = ("id", "title", "location", "worktype", "type", "payratemin", "payratemax", "applylink",
            "type-category-value")
    # A card spreads its data-job-* attributes over several elements; merge them per job id.
    for el in soup.select("[data-job-id]"):
        job_id = el.get("data-job-id")
        if not job_id:
            continue
        row = rows.setdefault(job_id, {"id": job_id})
        for k in keys:
            value = el.get(f"data-job-{k}")
            if value and not row.get(k):
                row[k] = value
    return list(rows.values())


class CuratelyMixin:
    MAX_PAGES = 80
    MAX_JOBS = 1500
    TIME_BUDGET_SECONDS = 50

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS
        raw, seen, page, complete = [], set(), 1, False
        while page <= self.MAX_PAGES and len(raw) < self.MAX_JOBS and loop.time() < deadline:
            html = await self.fetch_html(self.API_URL, params={"pageCount": str(page), "keyword": "",
                                                              "type": "", "aposLocale": "en"})
            rows = [r for r in curately_cards(html) if r["id"] not in seen]
            if not rows:
                complete = True
                break
            seen.update(r["id"] for r in rows)
            raw.extend(rows)
            page += 1
        jobs = self.parse_all(raw[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=page, complete=complete)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id, title = raw.get("id"), (raw.get("title") or "").strip()
        if not job_id or not title:
            return None
        link = raw.get("applylink") or ""
        link = quote(link, safe=":/?=&%#") if link else f"https://{self.BOARD}/?jobId={job_id}"

        def rate(key):
            try:
                return float(raw.get(key)) or None
            except (TypeError, ValueError):
                return None
        lo, hi = rate("payratemin"), rate("payratemax")
        period = ("hour" if (hi or lo or 0) < 500 else "year") if (lo or hi) else None
        return ScrapedJob(
            title=title,
            location=raw.get("location") or "",
            job_url=link,
            external_job_id=str(job_id),
            remote_type=remote_from(raw.get("worktype")),
            employment_type_raw=raw.get("type-category-value") or raw.get("type") or None,
            pay_rate_min=lo, pay_rate_max=hi, pay_period=period,
        )


register(BoardType(
    name="curately",
    mixin=CuratelyMixin,
    valid=lambda board: bool(HOST.fullmatch(board or "")),
    start_url=lambda board: f"https://{board}/api/v1/jobs/list",
    careers_url=lambda board: f"https://{board}/",
))
