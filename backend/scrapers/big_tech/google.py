"""
Google Jobs Scraper.

Uses Playwright for careers.google.com which is JavaScript-heavy.
"""

from datetime import datetime
from typing import Optional
import json
import re

from scrapers.base import (
    PlaywrightScraper,
    ScraperConfig,
    ScraperType,
    ScrapedJob,
    ScrapeResult,
)
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="big_tech")
class GoogleScraper(PlaywrightScraper):
    """Scraper for Google careers."""

    config = ScraperConfig(
        company_slug="google",
        company_name="Google",
        careers_url="https://careers.google.com/jobs/results/",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=10,
        page_timeout=45,
    )

    BASE_URL = "https://careers.google.com/jobs/results/"

    async def scrape(self) -> ScrapeResult:
        """Scrape Google careers using Playwright."""
        all_jobs = []
        page_num = 1

        page = await self.get_page()
        try:
            # Navigate to jobs page with filters
            url = f"{self.BASE_URL}?category=SOFTWARE_ENGINEERING&page={page_num}"
            await page.goto(url, wait_until="networkidle")

            while page_num <= self.config.max_pages:
                # Wait for job cards to load
                try:
                    await self.wait_for_jobs(page, "[data-job-id]", timeout=15000)
                except Exception:
                    self.logger.info("No more job cards found")
                    break

                # Extract jobs from the page
                job_cards = await page.query_selector_all("[data-job-id]")

                if not job_cards:
                    break

                for card in job_cards:
                    job = await self._parse_job_card(card)
                    if job:
                        all_jobs.append(job)

                # Check for next page
                next_btn = await page.query_selector('button[aria-label="Next page"]')
                if not next_btn or await next_btn.is_disabled():
                    break

                # Go to next page
                page_num += 1
                await page.goto(f"{self.BASE_URL}?category=SOFTWARE_ENGINEERING&page={page_num}")
                await page.wait_for_load_state("networkidle")

            return ScrapeResult(
                success=True,
                jobs=all_jobs,
                pages_scraped=page_num,
            )

        finally:
            await self.release_page(page)

    async def _parse_job_card(self, card) -> Optional[ScrapedJob]:
        """Parse a job card element."""
        try:
            job_id = await card.get_attribute("data-job-id")

            # Get title
            title_el = await card.query_selector("h2, h3, [class*='title']")
            title = await title_el.text_content() if title_el else ""

            # Get location
            location_el = await card.query_selector("[class*='location']")
            location = await location_el.text_content() if location_el else ""

            # Get link
            link_el = await card.query_selector("a")
            href = await link_el.get_attribute("href") if link_el else ""
            job_url = f"https://careers.google.com{href}" if href and not href.startswith("http") else href

            return ScrapedJob(
                title=self.clean_text(title) or "",
                location=self.clean_text(location) or "",
                job_url=job_url,
                external_job_id=job_id or "",
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job card: {e}")
            return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse raw job data (not used for Playwright scraper)."""
        return None
