"""
Jobvite career sites as job_boards rows (ats "jobvite").

Board: the company's Jobvite careersite name, the path segment of
jobs.jobvite.com/<board>/jobs (also the data-careersite of an embedded
Jobvite iframe), e.g. "ninjaone". The jobs page is server-rendered: one
table.jv-job-list per department (h3 above it), rows of
a[href="/<board>/job/<id>"] + td.jv-job-list-location; long boards page with
a jv-pagination "next" link. Descriptions live only on each job's page and
are left to the description backfill.
"""
import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import is_token, remote_from
from scrapers.base import ScrapedJob, ScrapeResult, UnexpectedResponseError

_JOB_HREF = re.compile(r"/job/([A-Za-z0-9]+)")


def jobvite_rows(html: str, base_url: str) -> tuple[List[dict], Optional[str]]:
    """([{id, title, url, location, department}], next page URL or None)."""
    soup = BeautifulSoup(html, "html.parser")
    rows, seen = [], set()
    for link in soup.select("a[href*='/job/']"):
        m = _JOB_HREF.search(link.get("href") or "")
        title = " ".join(link.get_text(" ", strip=True).split())
        if not m or not title or m.group(1) in seen:
            continue
        seen.add(m.group(1))
        row = link.find_parent("tr") or link.find_parent("li")
        loc_el = row.select_one(".jv-job-list-location") if row else None
        location = " ".join(loc_el.get_text(" ", strip=True).split()) if loc_el else ""
        parts = [p.strip() for p in location.split(",") if p.strip()]
        location = ", ".join(dict.fromkeys(parts))
        heading = link.find_previous(["h3", "h2"])
        department = " ".join(heading.get_text(" ", strip=True).split()) if heading and heading.name == "h3" else None
        rows.append({"id": m.group(1), "title": title, "url": urljoin(base_url, link["href"]),
                     "location": location, "department": department})
    nxt = soup.select_one("a.jv-pagination-next[href], .jv-pagination-next a[href]")
    return rows, (urljoin(base_url, nxt["href"]) if nxt else None)


class JobviteMixin:
    MAX_PAGES = 30
    MAX_JOBS = 1500

    async def scrape(self) -> ScrapeResult:
        url, raw, seen, pages = self.API_URL, [], set(), 0
        while url and pages < self.MAX_PAGES and len(raw) < self.MAX_JOBS:
            rows, url = jobvite_rows(await self.fetch_html(url), self.API_URL)
            if not rows and pages == 0:
                # Some boards send /jobs to the company's own iframe page (SiMa.ai);
                # ?nl=1 is Jobvite's plain list, without that redirect.
                rows, url = jobvite_rows(await self.fetch_html(f"{self.API_URL}?nl=1"), self.API_URL)
            pages += 1
            fresh = [r for r in rows if r["id"] not in seen]
            seen.update(r["id"] for r in fresh)
            raw.extend(fresh)
            if not fresh:
                break
        jobs = self.parse_all(raw[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=pages,
                            complete=url is None and len(raw) <= self.MAX_JOBS)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        if not raw.get("id") or not raw.get("title"):
            return None
        return ScrapedJob(
            title=raw["title"], location=raw.get("location") or "", job_url=raw["url"],
            external_job_id=raw["id"], department=raw.get("department"),
            remote_type=remote_from(raw.get("location")),
        )


register(BoardType(
    name="jobvite",
    mixin=JobviteMixin,
    valid=is_token,
    start_url=lambda board: f"https://jobs.jobvite.com/{board}/jobs",
    careers_url=lambda board: f"https://jobs.jobvite.com/{board}/jobs",
))
