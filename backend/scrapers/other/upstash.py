"""Upstash job scraper - hand-written roles on upstash.com/careers (no ATS)."""

import html as html_lib
import re
from typing import List, Optional

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry


# Moved to own careers page (no ATS; roles are static pages at upstash.com/careers/<slug>)
# (verified 2026-09-29). Roles tagged "Not actively hiring" are skipped.
@ScraperRegistry.register(category="other")
class UpstashScraper(HTTPScraper):
    """Scraper for Upstash careers (HTML role cards on upstash.com/careers)."""

    config = ScraperConfig(
        company_slug="upstash",
        company_name="Upstash",
        careers_url="https://upstash.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    BASE_URL = "https://upstash.com"
    CARD_RE = re.compile(r'<a[^>]*href="(/careers/[a-z0-9-]+)"[^>]*>(.*?)</a>', re.S)

    async def scrape(self) -> ScrapeResult:
        page = await self.fetch_html(self.config.careers_url)
        if not page:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data returned")
        cards = [
            {"path": m.group(1), "html": m.group(2)}
            for m in self.CARD_RE.finditer(page)
            if "not actively hiring" not in m.group(2).lower()
        ]
        all_jobs: List[ScrapedJob] = self.parse_all(cards)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    @staticmethod
    def _text(fragment: Optional[str]) -> str:
        return html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment or "")).strip()

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        card = raw["html"]
        title_m = re.search(r"<h[1-6][^>]*>(.*?)</h[1-6]>", card, re.S)
        title = self._text(title_m.group(1)) if title_m else ""
        if not title:
            return None
        summary_m = re.search(r"<p[^>]*>(.*?)</p>", card, re.S)
        slug = raw["path"].rsplit("/", 1)[-1]
        return ScrapedJob(
            title=title,
            location="Remote",  # role pages say "Work from anywhere"
            job_url=f"{self.BASE_URL}{raw['path']}",
            external_job_id=slug,
            job_description=self._text(summary_m.group(1)) if summary_m else None,
            remote_type="remote",
        )
