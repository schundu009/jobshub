"""
D. E. Shaw Research's own openings page as a job_boards row (ats "desres").

Board: "current-opportunities.html", the page on www.deshawresearch.com
that lists every opening as an <h5> title followed by a <ul> with the
description paragraphs and an "Apply Now" link to
apply.deshawresearch.com/careers/Register?pipelineId=<id> (the posting's own
application page, used as its URL). The page names no location per opening;
the group works from its New York City offices.
"""
import re
from typing import Optional
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from scrapers.ats import BoardType, register
from scrapers.base import ScrapedJob, ScrapeResult

SITE = "https://www.deshawresearch.com"
_PAGE = re.compile(r"[a-z0-9\-]{1,60}\.html")
_SALARY = re.compile(r"\$([\d,]{5,})\s*(?:–|-|&ndash;|to)\s*\$([\d,]{5,})")


def desres_rows(html: str) -> list:
    soup = BeautifulSoup(html or "", "html.parser")
    rows = []
    for h5 in soup.find_all("h5"):
        block = h5.find_next_sibling("ul")
        link = block.select_one("a[href*='pipelineId=']") if block else None
        if not link:
            continue
        pipeline = (parse_qs(urlparse(link["href"]).query).get("pipelineId") or [""])[0]
        paragraphs = [p for p in block.find_all("p")]
        rows.append({"id": pipeline, "title": h5.get_text(" ", strip=True), "url": link["href"],
                     "description": "".join(str(p) for p in paragraphs),
                     "text": " ".join(p.get_text(" ", strip=True) for p in paragraphs)})
    return rows


class DESRESMixin:
    async def scrape(self) -> ScrapeResult:
        jobs = self.parse_all(desres_rows(await self.fetch_html(self.API_URL)))
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=True)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        if not raw.get("id") or not raw.get("title"):
            return None
        text = raw.get("text") or ""
        m = _SALARY.search(text)
        lo, hi = (int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))) if m else (None, None)
        return ScrapedJob(
            title=raw["title"],
            location="New York, NY",
            job_url=raw["url"],
            external_job_id=raw["id"],
            job_description=raw.get("description") or None,
            salary_min=lo, salary_max=hi,
            remote_type="hybrid" if "hybrid" in text.lower() else None,
        )


register(BoardType(
    name="desres",
    mixin=DESRESMixin,
    valid=lambda board: bool(_PAGE.fullmatch(board or "")),
    start_url=lambda board: f"{SITE}/{board}",
    careers_url=lambda board: f"{SITE}/{board}",
))
