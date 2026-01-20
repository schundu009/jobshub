"""
Snap Inc. Jobs Scraper.

Uses Playwright for Snap's careers site.
"""

from datetime import datetime
from typing import Optional

from scrapers.base import (
    PlaywrightScraper,
    ScraperConfig,
    ScraperType,
    ScrapedJob,
    ScrapeResult,
)
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="enterprise")
class SnapScraper(PlaywrightScraper):
    """Scraper for Snap Inc. careers."""

    config = ScraperConfig(
        company_slug="snap",
        company_name="Snap Inc.",
        careers_url="https://careers.snap.com/jobs",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=10,
        page_timeout=45,
    )

    async def scrape(self) -> ScrapeResult:
        """Scrape Snap careers using Playwright."""
        all_jobs = []

        page = await self.get_page()
        try:
            await page.goto(f"{self.config.careers_url}?team=Engineering", wait_until="networkidle")

            # Wait for job cards
            await page.wait_for_selector(".job-card, [class*='JobCard'], [class*='job-listing']", timeout=15000)

            # Handle infinite scroll or pagination
            previous_count = 0
            for _ in range(20):
                cards = await page.query_selector_all(".job-card, [class*='JobCard'], [class*='job-listing']")
                if len(cards) == previous_count:
                    break
                previous_count = len(cards)
                await self.scroll_to_bottom(page, pause=1, max_scrolls=1)

            # Parse all cards
            cards = await page.query_selector_all(".job-card, [class*='JobCard'], [class*='job-listing']")
            for card in cards:
                job = await self._parse_job_card(card)
                if job:
                    all_jobs.append(job)

            return ScrapeResult(success=True, jobs=all_jobs, pages_scraped=1)

        finally:
            await self.release_page(page)

    async def _parse_job_card(self, card) -> Optional[ScrapedJob]:
        """Parse a job card element."""
        try:
            link_el = await card.query_selector("a")
            href = await link_el.get_attribute("href") if link_el else ""
            job_id = href.split("/")[-1] if href else ""

            job_url = f"https://careers.snap.com{href}" if href and not href.startswith("http") else href

            title_el = await card.query_selector("h3, h4, [class*='title']")
            title = await title_el.text_content() if title_el else ""

            location_el = await card.query_selector("[class*='location']")
            location = await location_el.text_content() if location_el else ""

            return ScrapedJob(
                title=self.clean_text(title) or "",
                location=self.clean_text(location) or "",
                job_url=job_url,
                external_job_id=job_id,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job card: {e}")
            return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        return None
