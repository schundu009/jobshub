"""
Teamtailor career sites as job_boards rows (ats "teamtailor").

Board: the career site's host, "careers.strativgroup.com" or
"<company>.teamtailor.com". Every Teamtailor site publishes its open jobs as
a JSON Feed at /jobs.json: {"items": [{id, title, url, date_published,
content_html, _jobposting (schema.org JobPosting: identifier, jobLocation[],
employmentType, ...)}]}.
"""
from datetime import datetime, timezone
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import HOST, join_place
from scrapers.base import ScrapedJob, ScrapeResult


_COUNTRY_NAMES = {
    "united kingdom", "united states", "germany", "france", "netherlands", "sweden", "norway", "denmark",
    "finland", "spain", "portugal", "italy", "ireland", "poland", "belgium", "switzerland", "austria",
    "canada", "australia", "india", "singapore", "japan", "brazil", "mexico", "czech republic", "estonia",
    "lithuania", "latvia", "romania", "greece", "hungary", "new zealand", "united arab emirates",
}


class TeamtailorMixin:
    async def scrape(self) -> ScrapeResult:
        jobs = self.parse_all(self.expect_list(await self.fetch_json(self.API_URL), "items"))
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=True)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        title, url = (raw.get("title") or "").strip(), raw.get("url")
        if not title or not url:
            return None
        posting = raw.get("_jobposting") or {}
        places = []
        locations = posting.get("jobLocation") or []
        for place in locations if isinstance(locations, list) else [locations]:
            addr = (place or {}).get("address") or {}
            region, country = addr.get("addressRegion"), addr.get("addressCountry")
            if region and country and len(str(country)) == 2 and region.lower() in _COUNTRY_NAMES:
                # Teamtailor puts the country's name in addressRegion and its code in addressCountry.
                region, country = None, region
            name = join_place(addr.get("addressLocality"), region, country)
            if name and name not in places:
                places.append(name)
        remote = "remote" if str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE" else None
        if not places and remote:
            places = ["Remote"]
        ident = (posting.get("identifier") or {}).get("value")
        posted = None
        stamp = raw.get("date_published") or posting.get("datePosted")
        if stamp:
            try:
                posted = datetime.fromisoformat(stamp.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)
            except ValueError:
                posted = None
        emp = posting.get("employmentType")
        return ScrapedJob(
            title=title,
            location="; ".join(places[:3]) + (f" (+{len(places) - 3} more)" if len(places) > 3 else ""),
            job_url=url,
            external_job_id=str(ident or raw.get("id")),
            job_description=raw.get("content_html") or posting.get("description") or None,
            posted_date=posted,
            remote_type=remote,
            employment_type_raw=(", ".join(emp) if isinstance(emp, list) else emp) or None,
        )


register(BoardType(
    name="teamtailor",
    mixin=TeamtailorMixin,
    valid=lambda board: bool(HOST.fullmatch(board or "")),
    start_url=lambda board: f"https://{board}/jobs.json",
    careers_url=lambda board: f"https://{board}/jobs",
))
