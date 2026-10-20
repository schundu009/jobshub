"""
Keka Hire career portals as job_boards rows (ats "keka").

Board: "<subdomain>/<portal id>", from <subdomain>.keka.com/careers and the
portal id its page embeds (".../careerportal/..." and the embed-jobs API),
e.g. "relanto/02b7fe40-b031-4feb-9965-e44257ddd8e5". One call lists every
active job with its description:
GET <subdomain>.keka.com/careers/api/embedjobs/default/active/<portal id>
-> [{id, title, description, departmentName, jobLocations[{name, city, state,
countryName}], experience, publishedOn, ...}]. A job opens at
<subdomain>.keka.com/careers/jobdetails/<id>.
"""
import re
from datetime import datetime, timezone
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.base import ScrapedJob, ScrapeResult

_SUB = re.compile(r"[a-z0-9][a-z0-9\-]{0,62}")
_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def _parts(board: str):
    sub, _, portal = (board or "").partition("/")
    return (sub, portal.lower()) if _SUB.fullmatch(sub) and _UUID.fullmatch(portal.lower()) else None


class KekaMixin:
    async def scrape(self) -> ScrapeResult:
        jobs = self.parse_all(self.expect_list(await self.fetch_json(self.API_URL)))
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=True)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id, title = raw.get("id"), (raw.get("title") or "").strip()
        if not job_id or not title:
            return None
        sub = _parts(self.BOARD)[0]
        places = [l.get("name") or ", ".join(p for p in (l.get("city"), l.get("countryName")) if p)
                  for l in raw.get("jobLocations") or []]
        places = [p for p in dict.fromkeys(places) if p]
        posted = None
        if raw.get("publishedOn"):
            try:
                posted = datetime.fromisoformat(raw["publishedOn"].replace("Z", "+00:00")).astimezone(
                    timezone.utc).replace(tzinfo=None)
            except ValueError:
                posted = None
        return ScrapedJob(
            title=title,
            location="; ".join(places[:3]),
            job_url=f"https://{sub}.keka.com/careers/jobdetails/{job_id}",
            external_job_id=str(job_id),
            job_description=raw.get("description") or None,
            department=raw.get("departmentName") or None,
            posted_date=posted,
            extra={"experience": raw.get("experience"), "skills": raw.get("skillNames") or []},
        )


register(BoardType(
    name="keka",
    mixin=KekaMixin,
    valid=lambda board: _parts(board) is not None,
    start_url=lambda board: "https://{0}.keka.com/careers/api/embedjobs/default/active/{1}".format(*_parts(board)),
    careers_url=lambda board: f"https://{_parts(board)[0]}.keka.com/careers/",
))
