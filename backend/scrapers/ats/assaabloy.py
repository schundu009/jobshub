"""
ASSA ABLOY's own job feed as a job_boards row (ats "assaabloy").

The group's career site (www.assaabloy.com/career/<lang>/open-positions)
renders every opening from one public JSON file,
integration-hub-prod-assets.globalweb.aws.assaabloy.com/job-openings/jobs.json
({"itemsTotalCount", "items": [{jobReqId, title, postStartDate, locations[],
jobFunction, applicationUrl (SuccessFactors career2.successfactors.eu)}]}).
Each opening's page is <career site>/open-positions/job.<jobReqId>.
The applications run on SuccessFactors, whose own search the site does not use.

Board: the career site's language, "en".
"""
import re
from datetime import datetime, timezone
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.base import ScrapedJob, ScrapeResult

FEED_URL = "https://integration-hub-prod-assets.globalweb.aws.assaabloy.com/job-openings/jobs.json"
_LANG = re.compile(r"[a-z]{2}(?:-[a-z]{2})?")


def _site(board: str) -> str:
    return f"https://www.assaabloy.com/career/{board}/open-positions"


class AssaAbloyFeedMixin:
    MAX_JOBS = 3000

    async def scrape(self) -> ScrapeResult:
        data = await self.fetch_json(self.API_URL)
        items = self.expect_list(data, "items")
        jobs = self.parse_all(items[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=len(items) <= self.MAX_JOBS)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id = str(raw.get("jobReqId") or "").strip()
        title = (raw.get("title") or "").strip()
        if not job_id or not title:
            return None
        places = []
        for loc in raw.get("locations") or []:
            place = ", ".join(p for p in (loc.get("city"), loc.get("state"), loc.get("country")) if p)
            if place and place not in places:
                places.append(place)
        location = "; ".join(places[:3]) + (f" (+{len(places) - 3} more)" if len(places) > 3 else "")
        posted = None
        try:
            posted = datetime.fromisoformat(raw.get("postStartDate") or raw.get("created") or "")
            posted = posted.astimezone(timezone.utc).replace(tzinfo=None)
        except ValueError:
            posted = None
        office = str(raw.get("officePresence") or "").lower()
        remote = next((k for k in ("remote", "hybrid") if k in office), None) or ("on-site" if "site" in office else None)
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"{_site(self.BOARD)}/job.{job_id}",
            external_job_id=job_id,
            department=(raw.get("jobFunction") or {}).get("category") or None,
            posted_date=posted,
            remote_type=remote,
            extra={"apply_url": raw.get("applicationUrl"),
                   "experience_level": (raw.get("experienceLevel") or {}).get("name")},
        )


register(BoardType(
    name="assaabloy",
    mixin=AssaAbloyFeedMixin,
    valid=lambda board: bool(_LANG.fullmatch(board or "")),
    start_url=lambda board: FEED_URL,
    careers_url=_site,
))
