"""
Apex Systems - US postings.

Source: the server-rendered US job table at
``https://www.apexsystems.com/search-results-usa?page=N`` (Drupal pager, 0-based,
25 rows per page, newest first) - title, city, state, date posted, link. The
listing has no job type or pay (those are only on each job page, which is not
fetched), so employment_type_raw is left empty rather than guessed.
robots.txt allows /search-results-usa and /job/ (it disallows /search/).
Public posting URL: https://www.apexsystems.com/job/{id}_usa/{slug}.
Disabled 2026-09-29: see the ScraperConfig note (Cloudflare challenge).
"""

import re

from bs4 import BeautifulSoup

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_state, join_location, parse_iso

SITE = "https://www.apexsystems.com"
LIST_URL = f"{SITE}/search-results-usa"
_JOB_HREF_RE = re.compile(r"^/job/([^/]+)/")


def parse_apex_listing(html: str) -> list[dict]:
    """Rows of the search-results table -> [{id, title, city, state, posted, url}]."""
    soup = BeautifulSoup(html, "html.parser")
    rows = []
    for tr in soup.select("tbody tr"):
        link = tr.select_one("a.job-title-link")
        cells = tr.find_all("td")
        if not link or len(cells) < 4:
            continue
        href = link.get("href") or ""
        m = _JOB_HREF_RE.match(href)
        if not m:
            continue
        rows.append({
            "id": m.group(1),
            "title": link.get_text(" ", strip=True),
            "city": cells[1].get_text(" ", strip=True),
            "state": cells[2].get_text(" ", strip=True),
            "posted": cells[3].get_text(" ", strip=True),
            "url": SITE + href,
        })
    return rows


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class ApexSystemsScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="apexsystems",
        company_name="Apex Systems",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        # 2026-09-29: pages 0-1 come from cache, but every later page answers with
        # a Cloudflare JS challenge instead of the table. Solving challenges is
        # out of bounds, so this stays off until Apex exposes a plain listing.
        enabled=False,
        disabled_reason="Cloudflare JS challenge on listing pages after the first two",
    )
    AGENCY_NAME = "Apex Systems"
    MAX_PAGES = 120

    async def fetch_raw(self) -> list:
        raw, seen = [], set()
        for page in range(self.MAX_PAGES):
            html = await self._http("GET", LIST_URL, params={"page": str(page)} if page else None,
                                    expect="text")
            rows = [r for r in parse_apex_listing(html) if r["id"] not in seen]
            seen.update(r["id"] for r in rows)
            raw.extend(rows)
            if not rows or len(raw) >= self.MAX_JOBS or self.out_of_time():
                break
        return raw

    def parse_job(self, raw: dict):
        state = raw.get("state")
        if state and not is_us_state(state):
            return None
        return self.make_job(
            title=raw.get("title"),
            location=join_location(raw.get("city"), state),
            job_url=raw.get("url"),
            external_job_id=raw.get("id"),
            posted_date=parse_iso(raw.get("posted")),
        )
