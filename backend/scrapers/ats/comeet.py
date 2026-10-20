"""
Comeet career pages as job_boards rows (ats "comeet").

Board: "<company uid>/<token>", the two values the employer's careers page
sends to the Comeet careers API (e.g. "34.006/436150E150E0CA221B01D7A21B043621B0";
the token is the public one in the page). One call lists every position:
GET comeet.co/careers-api/2.0/company/<uid>/positions?token=<token>&details=true
-> [{uid, name, department, location{name, city, state, country, is_remote},
employment_type, workplace_type, url_active_page, url_comeet_hosted_page,
time_updated, details: [{name, value(html)}]}].
"""
import html
import re
from datetime import datetime, timezone
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import join_place, remote_from
from scrapers.base import ScrapedJob, ScrapeResult

_UID = re.compile(r"[0-9A-Fa-f]{1,4}\.[0-9A-Fa-f]{1,4}")
_TOKEN = re.compile(r"[0-9A-Za-z]{10,80}")


def _parts(board: str):
    uid, _, token = (board or "").partition("/")
    return (uid, token) if _UID.fullmatch(uid) and _TOKEN.fullmatch(token) else None


class ComeetMixin:
    async def scrape(self) -> ScrapeResult:
        uid, token = _parts(self.BOARD)
        data = await self.fetch_json(self.API_URL, params={"token": token, "details": "true"})
        jobs = self.parse_all(self.expect_list(data))
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=True)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        uid, title = raw.get("uid"), (raw.get("name") or "").strip()
        if not uid or not title:
            return None
        loc = raw.get("location") or {}
        location = loc.get("name") or join_place(loc.get("city"), loc.get("state"), loc.get("country"))
        sections = []
        for item in raw.get("details") or []:
            if isinstance(item, dict) and (item.get("value") or "").strip():
                heading = (item.get("name") or "").strip()
                sections.append((f"<h3>{html.escape(heading)}</h3>" if heading else "") + item["value"])
        posted = None
        if raw.get("time_updated"):
            try:
                posted = datetime.fromisoformat(raw["time_updated"].replace("Z", "+00:00")).astimezone(
                    timezone.utc).replace(tzinfo=None)
            except ValueError:
                posted = None
        return ScrapedJob(
            title=title, location=location or "",
            job_url=raw.get("url_active_page") or raw.get("url_comeet_hosted_page") or "",
            external_job_id=str(uid),
            job_description="\n".join(sections) or None,
            department=raw.get("department") or None,
            posted_date=posted,
            remote_type="remote" if loc.get("is_remote") else remote_from(raw.get("workplace_type")),
            employment_type_raw=raw.get("employment_type") or None,
        )


register(BoardType(
    name="comeet",
    mixin=ComeetMixin,
    valid=lambda board: _parts(board) is not None,
    start_url=lambda board: f"https://www.comeet.co/careers-api/2.0/company/{_parts(board)[0]}/positions",
))
