"""
TalentLyft career sites as job_boards rows (ats "talentlyft").

Board: the subdomain of <board>.talentlyft.com, e.g. "kpmg-bulgaria". The
site's job list is an HTML fragment its page fetches with
X-Requested-With: XMLHttpRequest from /JobList?...&page=N&pageSize=M:
a.jobs__box[href=<site>/jobs/<slug>][id=<job id>] with h3.jobs__box__heading
(title) and p.jobs__box__text ("City, Country (Hybrid)").
"""
import re
from typing import Optional

from bs4 import BeautifulSoup

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import remote_from
from scrapers.base import ScrapedJob, ScrapeResult

_SUB = re.compile(r"[a-z0-9][a-z0-9\-]{0,62}")


def _site(board: str) -> str:
    return f"https://{board}.talentlyft.com"


def talentlyft_rows(html: str) -> list:
    soup = BeautifulSoup(html or "", "html.parser")
    rows = []
    for box in soup.select("a.jobs__box[href]"):
        title = box.select_one(".jobs__box__heading")
        text = box.select_one(".jobs__box__text")
        rows.append({
            "id": box.get("id") or box["href"].rstrip("/").rsplit("/", 1)[-1],
            "url": box["href"],
            "title": title.get_text(" ", strip=True) if title else "",
            "location": text.get_text(" ", strip=True) if text else "",
        })
    return rows


class TalentLyftMixin:
    PAGE_SIZE = 50
    MAX_PAGES = 30

    def _params(self, page: int) -> dict:
        site = _site(self.BOARD)
        return {"layoutId": "Jobs-2", "websiteUrl": site, "themeId": "2", "language": "en",
                "subdomain": self.BOARD, "page": str(page), "pageSize": str(self.PAGE_SIZE), "contains": ""}

    async def scrape(self) -> ScrapeResult:
        raw, seen, page, complete = [], set(), 1, False
        while page <= self.MAX_PAGES:
            html = await self._request("GET", self.API_URL, lambda r: r.text(), params=self._params(page),
                                       headers={"X-Requested-With": "XMLHttpRequest"})
            rows = [r for r in talentlyft_rows(html) if r["id"] not in seen]
            seen.update(r["id"] for r in rows)
            raw.extend(rows)
            if len(rows) < self.PAGE_SIZE:
                complete = True
                break
            page += 1
        jobs = self.parse_all(raw)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=page, complete=complete)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        if not raw.get("id") or not raw.get("title") or not raw.get("url"):
            return None
        location = raw.get("location") or ""
        remote = remote_from(location)
        clean = re.sub(r"\s*\((?:hybrid|remote|on-?site)\)\s*$", "", location, flags=re.I).strip()
        return ScrapedJob(title=raw["title"], location=clean or location, job_url=raw["url"],
                          external_job_id=str(raw["id"]), remote_type=remote)


register(BoardType(
    name="talentlyft",
    mixin=TalentLyftMixin,
    valid=lambda board: bool(_SUB.fullmatch(board or "")),
    start_url=lambda board: f"{_site(board)}/JobList",
    careers_url=lambda board: f"{_site(board)}/",
))
