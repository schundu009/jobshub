"""
Sprockets job boards as job_boards rows (ats "sprockets").

Board: the board identifier of jobs.sprockets.ai/<locale>/<board>/jobs, e.g.
"pyramidinc" (locale en-US), or "<locale>/<board>". The board page is
rendered on the server: its Apollo SSR data carries the GetJobsForBoard
result, {"data": {"jobBoardPostingPaginated": {"totalCount", "nodes": [{id,
jobDescription, employmentType, workplaceType, wageMin/Max, wageInterval,
postedAt, accountSubtitle, group{name (the title), location{name}}}]}}}, and
the page honours ?page=N&itemsPer=M. Its GraphQL API needs a session, so
the pages themselves are read. A posting opens at <board page>/<id>.
"""
import json
import re
from datetime import datetime, timezone
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import remote_from
from scrapers.base import ScrapedJob, ScrapeResult, UnexpectedResponseError

_LOCALE = re.compile(r"[a-z]{2}-[A-Z]{2}")
_IDENT = re.compile(r"[A-Za-z0-9_\-]{1,80}")
_RESULT = re.compile(r'\{"data":\s*\{"jobBoardPostingPaginated"')


def _parts(board: str):
    locale, _, ident = (board or "").rpartition("/")
    locale = locale or "en-US"
    return (locale, ident) if _LOCALE.fullmatch(locale) and _IDENT.fullmatch(ident) else None


def _jobs_page(board: str) -> str:
    return "https://jobs.sprockets.ai/{0}/{1}/jobs".format(*_parts(board))


def sprockets_page(html: str) -> dict:
    """The jobBoardPostingPaginated result embedded in a board page ({} when absent)."""
    m = _RESULT.search(html or "")
    if not m:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(html[m.start():])
    except ValueError:
        return {}
    return (data.get("data") or {}).get("jobBoardPostingPaginated") or {}


class SprocketsMixin:
    PER_PAGE = 100
    MAX_JOBS = 1500

    async def scrape(self) -> ScrapeResult:
        raw, seen, total, page = [], set(), None, 1
        while len(raw) < self.MAX_JOBS:
            result = sprockets_page(await self.fetch_html(self.API_URL, params={
                "page": str(page), "itemsPer": str(self.PER_PAGE)}))
            if not result and page == 1:
                raise UnexpectedResponseError("Sprockets board page had no job data")
            nodes = [n for n in result.get("nodes") or [] if n.get("id") not in seen]
            total = int(result.get("totalCount") or 0)
            seen.update(n.get("id") for n in nodes)
            raw.extend(nodes)
            if not nodes or len(raw) >= total:
                break
            page += 1
        jobs = self.parse_all(raw[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=page,
                            complete=total is not None and len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        group = raw.get("group") or {}
        job_id, title = raw.get("id"), (group.get("name") or "").strip()
        if not job_id or not title:
            return None
        location = (group.get("location") or {}).get("name") or ""
        posted = None
        if raw.get("postedAt"):
            try:
                posted = datetime.fromisoformat(raw["postedAt"].replace("Z", "+00:00")).astimezone(
                    timezone.utc).replace(tzinfo=None)
            except ValueError:
                posted = None

        def wage(key):
            try:
                return float(raw.get(key)) or None
            except (TypeError, ValueError):
                return None
        interval = str(raw.get("wageInterval") or "").lower()
        period = {"hourly": "hour", "daily": "day", "weekly": "week", "monthly": "month",
                  "yearly": "year", "annually": "year", "annual": "year"}.get(interval)
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"{_jobs_page(self.BOARD)}/{job_id}",
            external_job_id=str(job_id),
            job_description=raw.get("jobDescription") or None,
            posted_date=posted,
            remote_type=remote_from(raw.get("workplaceType")),
            employment_type_raw=(raw.get("employmentType") or "").replace("_", " ") or None,
            pay_rate_min=wage("wageMin"), pay_rate_max=wage("wageMax"), pay_period=period,
            extra={"subtitle": raw.get("accountSubtitle")},
        )


register(BoardType(
    name="sprockets",
    mixin=SprocketsMixin,
    valid=lambda board: _parts(board) is not None,
    start_url=_jobs_page,
    careers_url=_jobs_page,
))
