"""
Revolut Jobs Scraper.

Parses the positions list embedded in www.revolut.com/careers/ (Next.js).
"""

import json
import re
from typing import Optional

from scrapers.base import (
    HTTPScraper,
    ScraperConfig,
    ScraperType,
    ScrapedJob,
    ScrapeResult,
    UnexpectedResponseError,
)
from scrapers.registry import ScraperRegistry


# Moved to Revolut's own careers site (verified 2026-09-29): the Greenhouse
# board is gone. www.revolut.com/careers/ is a Next.js page whose
# __NEXT_DATA__ props carry every open position (pageProps.positions, ~380,
# matching the careers-teams-widget total). The site is behind a bot check
# that 403s requests without browser-like sec-fetch/sec-ch-ua headers.
@ScraperRegistry.register(category="finance")
class RevolutScraper(HTTPScraper):
    """Scraper for Revolut careers (positions embedded in the careers page)."""

    config = ScraperConfig(
        company_slug="revolut",
        company_name="Revolut",
        careers_url="https://www.revolut.com/careers/",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        request_timeout=45,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "en-GB,en;q=0.9",
            "sec-ch-ua": '"Chromium";v="140", "Google Chrome";v="140"',
            "sec-ch-ua-platform": '"macOS"',
            "sec-fetch-dest": "document",
            "sec-fetch-mode": "navigate",
            "sec-fetch-site": "none",
            "upgrade-insecure-requests": "1",
        },
    )

    PAGE_URL = "https://www.revolut.com/careers/"
    JOB_URL = "https://www.revolut.com/careers/position/{slug}-{id}/"
    MAX_JOBS = 1500
    _NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', re.S)

    async def scrape(self) -> ScrapeResult:
        html = await self.fetch_html(self.PAGE_URL)
        positions = self.extract_positions(html)
        jobs = self.parse_all(positions[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=1)

    def extract_positions(self, html: str) -> list:
        match = self._NEXT_DATA_RE.search(html or "")
        if not match:
            raise UnexpectedResponseError("Revolut careers page has no __NEXT_DATA__ (bot check?)")
        try:
            data = json.loads(match.group(1))
        except ValueError as e:
            raise UnexpectedResponseError(f"Revolut __NEXT_DATA__ is not JSON: {e}")
        page_props = (data.get("props") or {}).get("pageProps") or {}
        return self.expect_list(page_props, "positions")

    @staticmethod
    def slugify(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-") or "position"

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id = str(raw.get("id") or "")
        title = (raw.get("text") or "").strip()
        if not job_id or not title:
            return None
        locations = [loc for loc in (raw.get("locations") or []) if isinstance(loc, dict)]
        names = [loc.get("name") for loc in locations if loc.get("name")]
        # Only flag fully-remote roles; mixed office/remote lists stay unset.
        types = {loc.get("type") for loc in locations}
        remote_type = "remote" if types == {"remote"} else None
        return ScrapedJob(
            title=title,
            location="; ".join(names),
            job_url=self.JOB_URL.format(slug=self.slugify(title), id=job_id),
            external_job_id=job_id,
            job_description=self.clean_html(raw.get("description")) or None,
            department=raw.get("team") or None,
            remote_type=remote_type,
        )
