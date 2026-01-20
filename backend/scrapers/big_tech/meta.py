"""
Meta (Facebook) Jobs Scraper.

Uses Playwright for metacareers.com which requires JavaScript.
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


@ScraperRegistry.register(category="big_tech")
class MetaScraper(PlaywrightScraper):
    """Scraper for Meta careers."""

    config = ScraperConfig(
        company_slug="meta",
        company_name="Meta",
        careers_url="https://www.metacareers.com/jobs",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=10,
        page_timeout=45,
    )

    BASE_URL = "https://www.metacareers.com/jobs"

    async def scrape(self) -> ScrapeResult:
        """Scrape Meta careers using Playwright."""
        all_jobs = []
        pages_scraped = 0

        page = await self.get_page()
        try:
            # Navigate to jobs page
            await page.goto(self.BASE_URL, wait_until="networkidle")

            # Wait for jobs to load
            await page.wait_for_selector("[data-testid='job-card'], .job-card, [class*='JobCard']", timeout=15000)

            # Handle infinite scroll
            previous_count = 0
            scroll_attempts = 0
            max_scrolls = 20

            while scroll_attempts < max_scrolls:
                # Get current job cards
                cards = await page.query_selector_all("[data-testid='job-card'], .job-card, [class*='JobCard']")
                current_count = len(cards)

                if current_count == previous_count:
                    scroll_attempts += 1
                    if scroll_attempts >= 3:
                        break
                else:
                    scroll_attempts = 0

                previous_count = current_count

                # Scroll to load more
                await self.scroll_to_bottom(page, pause=1.5, max_scrolls=1)
                pages_scraped += 1

            # Parse all job cards
            cards = await page.query_selector_all("[data-testid='job-card'], .job-card, [class*='JobCard']")

            for card in cards:
                job = await self._parse_job_card(card)
                if job:
                    all_jobs.append(job)

            return ScrapeResult(
                success=True,
                jobs=all_jobs,
                pages_scraped=pages_scraped,
            )

        finally:
            await self.release_page(page)

    async def _parse_job_card(self, card) -> Optional[ScrapedJob]:
        """Parse a job card element."""
        try:
            # Get job link and ID
            link_el = await card.query_selector("a")
            href = await link_el.get_attribute("href") if link_el else ""

            # Extract job ID from URL
            job_id = ""
            if href:
                parts = href.split("/")
                job_id = parts[-1] if parts else ""

            job_url = f"https://www.metacareers.com{href}" if href and not href.startswith("http") else href

            # Get title
            title_el = await card.query_selector("h3, h4, [class*='title'], [class*='Title']")
            title = await title_el.text_content() if title_el else ""

            # Get location
            location_el = await card.query_selector("[class*='location'], [class*='Location']")
            location = await location_el.text_content() if location_el else ""

            # Get team/department
            team_el = await card.query_selector("[class*='team'], [class*='Team']")
            team = await team_el.text_content() if team_el else ""

            return ScrapedJob(
                title=self.clean_text(title) or "",
                location=self.clean_text(location) or "",
                job_url=job_url,
                external_job_id=job_id,
                department=self.clean_text(team),
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job card: {e}")
            return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse raw job data (not used for Playwright scraper)."""
        return None
