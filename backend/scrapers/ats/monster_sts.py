"""
Monster STS staffing-firm job sites as job_boards rows (ats "monster-sts").

Board: the firm's site host, e.g. "www.thefountaingroup.com". Its search
page loads GET /api/requisitions/search?defaultFeed=true&page=N (20 a page),
an HTML fragment: "Results (1–20 of 532)" and li.tr rows with a.btn-link
(title, href /job/<id>/<slug>), .job-salary, .job-posting-date, .job-reqid,
.job-location and a short .job-description teaser.
"""
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import HOST, remote_from
from scrapers.base import ScrapedJob, ScrapeResult

_JOB = re.compile(r"/job/(\d+)/")
_TOTAL = re.compile(r"of\s+([\d,]+)\s*\)")
_PAY = re.compile(r"\$([\d,.]+)(?:\s*to\s*\$([\d,.]+))?")
_PAY_UNIT = re.compile(r"\b(Hourly|Daily|Weekly|Monthly|Yearly|Annually|Annual)\b", re.I)


def sts_page(html: str, base: str) -> tuple[list, Optional[int]]:
    soup = BeautifulSoup(html or "", "html.parser")
    heading = soup.select_one(".results-heading")
    m = _TOTAL.search(heading.get_text(" ", strip=True)) if heading else None
    rows = []
    for li in soup.select(".job-search-results li.tr"):
        link = li.select_one(".job-title a[href]") or li.select_one("a[href*='/job/']")
        jm = _JOB.search(link.get("href") if link else "")
        if not link or not jm:
            continue

        def text(cls):
            el = li.select_one(f".{cls}")
            return " ".join(el.get_text(" ", strip=True).split()) if el else ""
        rows.append({"id": jm.group(1), "url": urljoin(base, link["href"]), "title": text("job-title"),
                     "location": text("job-location"), "salary": text("job-salary"),
                     "date": text("job-posting-date"), "reqid": text("job-reqid"),
                     "teaser": text("job-description")})
    return rows, (int(m.group(1).replace(",", "")) if m else None)


class MonsterSTSMixin:
    MAX_PAGES = 80
    MAX_JOBS = 1500

    async def scrape(self) -> ScrapeResult:
        base = f"https://{self.BOARD}/"
        raw, seen, total, page = [], set(), None, 1
        while page <= self.MAX_PAGES and len(raw) < self.MAX_JOBS:
            rows, count = sts_page(await self.fetch_html(self.API_URL, params={
                "defaultFeed": "true", "page": str(page)}), base)
            total = count if count is not None else total
            fresh = [r for r in rows if r["id"] not in seen]
            seen.update(r["id"] for r in fresh)
            raw.extend(fresh)
            if not fresh or (total is not None and len(raw) >= total):
                break
            page += 1
        jobs = self.parse_all(raw[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=page,
                            complete=total is not None and len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        if not raw.get("id") or not raw.get("title"):
            return None
        lo = hi = period = None
        m = _PAY.search(raw.get("salary") or "")
        if m:
            lo = float(m.group(1).replace(",", ""))
            hi = float(m.group(2).replace(",", "")) if m.group(2) else lo
            u = _PAY_UNIT.search(raw.get("salary") or "")
            unit = u.group(1).lower() if u else ""
            period = {"hourly": "hour", "daily": "day", "weekly": "week", "monthly": "month"}.get(
                unit, "year" if unit else None)
        posted = None
        try:
            posted = datetime.strptime(raw.get("date") or "", "%m/%d/%Y")
        except ValueError:
            posted = None
        return ScrapedJob(
            title=raw["title"], location=raw.get("location") or "", job_url=raw["url"],
            external_job_id=raw["id"], posted_date=posted, remote_type=remote_from(raw.get("location")),
            pay_rate_min=lo, pay_rate_max=hi, pay_period=period,
            extra={"req_id": raw.get("reqid")},
        )


register(BoardType(
    name="monster-sts",
    mixin=MonsterSTSMixin,
    valid=lambda board: bool(HOST.fullmatch(board or "")),
    start_url=lambda board: f"https://{board}/api/requisitions/search",
    careers_url=lambda board: f"https://{board}/search",
))
