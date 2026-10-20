"""
Gem job boards as job_boards rows (ats "gem").

Board: the board slug of jobs.gem.com/<board>, e.g. "groq". One call lists
every post with its description:
GET api.gem.com/job_board/v0/<board>/job_posts/
-> [{id, title, absolute_url, content (html), location{name}, location_type,
departments[{name}], employment_type, first_published_at, requisition_id}].
"""
from datetime import datetime, timezone
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import is_token, remote_from
from scrapers.base import ScrapedJob, ScrapeResult


class GemMixin:
    async def scrape(self) -> ScrapeResult:
        jobs = self.parse_all(self.expect_list(await self.fetch_json(self.API_URL)))
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=True)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id, title = raw.get("id"), (raw.get("title") or "").strip()
        if not job_id or not title:
            return None
        posted = None
        stamp = raw.get("first_published_at") or raw.get("created_at")
        if stamp:
            try:
                posted = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                posted = None
        departments = [d.get("name") for d in raw.get("departments") or [] if isinstance(d, dict) and d.get("name")]
        return ScrapedJob(
            title=title,
            location=(raw.get("location") or {}).get("name") or "",
            job_url=raw.get("absolute_url") or f"https://jobs.gem.com/{self.BOARD}/{job_id}",
            external_job_id=str(job_id),
            job_description=raw.get("content") or raw.get("content_plain") or None,
            department=departments[0] if departments else None,
            posted_date=posted,
            remote_type=remote_from(raw.get("location_type")),
            employment_type_raw=raw.get("employment_type") or None,
            extra={"requisition_id": raw.get("requisition_id")},
        )


register(BoardType(
    name="gem",
    mixin=GemMixin,
    valid=is_token,
    start_url=lambda board: f"https://api.gem.com/job_board/v0/{board}/job_posts/",
    careers_url=lambda board: f"https://jobs.gem.com/{board}",
))
