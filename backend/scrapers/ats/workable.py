"""
Workable boards as job_boards rows (ats "workable").

Board: the account slug of apply.workable.com/<board>/ (a posting link
apply.workable.com/j/<shortcode> resolves to it), e.g. "innovaccer-analytics".
One call lists every published job with its description:
GET apply.workable.com/api/v1/widget/accounts/<board>?details=true
-> {"name", "jobs": [{title, shortcode, url, department, city, state,
country, telecommuting, employment_type, published_on, description, ...}]}.
"""
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import is_token, join_place
from scrapers.base import ScrapedJob, ScrapeResult


class WorkableMixin:
    async def scrape(self) -> ScrapeResult:
        data = await self.fetch_json(self.API_URL, params={"details": "true"})
        jobs = self.parse_all(self.expect_list(data, "jobs"))
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=True)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        code = raw.get("shortcode")
        title = (raw.get("title") or "").strip()
        if not code or not title:
            return None
        places = [join_place(l.get("city"), l.get("region"), l.get("country"))
                  for l in raw.get("locations") or [] if not l.get("hidden")]
        places = [p for p in dict.fromkeys(places) if p] or [join_place(raw.get("city"), raw.get("state"), raw.get("country"))]
        location = "; ".join(places[:3])
        if raw.get("telecommuting") and "remote" not in location.lower():
            location = f"Remote ({location})" if location else "Remote"
        return ScrapedJob(
            title=title, location=location,
            job_url=raw.get("url") or f"https://apply.workable.com/j/{code}",
            external_job_id=str(code),
            job_description=raw.get("description") or None,
            department=raw.get("department") or None,
            posted_date=self.parse_date(raw.get("published_on") or raw.get("created_at")),
            remote_type="remote" if raw.get("telecommuting") else None,
            employment_type_raw=raw.get("employment_type") or None,
        )


register(BoardType(
    name="workable",
    mixin=WorkableMixin,
    valid=is_token,
    start_url=lambda board: f"https://apply.workable.com/api/v1/widget/accounts/{board}",
    careers_url=lambda board: f"https://apply.workable.com/{board}/",
))
