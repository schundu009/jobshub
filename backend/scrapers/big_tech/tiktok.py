"""
TikTok Jobs Scraper.

Uses Playwright for careers.tiktok.com.
"""

from datetime import datetime
from typing import Optional
import json

from scrapers.base import (
    PlaywrightScraper,
    ScraperConfig,
    ScraperType,
    ScrapedJob,
    ScrapeResult,
)
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="big_tech")
class TikTokScraper(PlaywrightScraper):
    """Scraper for TikTok careers."""

    config = ScraperConfig(
        company_slug="tiktok",
        company_name="TikTok",
        careers_url="https://careers.tiktok.com/position",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=10,
        page_timeout=45,
    )

    BASE_URL = "https://careers.tiktok.com/position"

    async def scrape(self) -> ScrapeResult:
        """Scrape TikTok careers using Playwright."""
        all_jobs = []
        page_num = 1

        page = await self.get_page()
        try:
            # Navigate to jobs page with engineering filter
            url = f"{self.BASE_URL}?keywords=&category=6704215862603155720&location=&project=&type=&job_hot_flag=&current={page_num}&limit=50"
            await page.goto(url, wait_until="networkidle")

            while page_num <= self.config.max_pages:
                # Wait for job list to load
                try:
                    await page.wait_for_selector(".position-list, [class*='job-card'], [class*='JobCard']", timeout=15000)
                except Exception:
                    self.logger.info("Job list not found")
                    break

                # Get job cards
                cards = await page.query_selector_all(".position-item, .job-item, [class*='job-card']")

                if not cards:
                    break

                for card in cards:
                    job = await self._parse_job_card(card)
                    if job:
                        all_jobs.append(job)

                # Check for next page button
                next_btn = await page.query_selector(".pagination-next:not(.disabled), [class*='next']:not([disabled])")
                if not next_btn:
                    break

                page_num += 1
                url = f"{self.BASE_URL}?keywords=&category=6704215862603155720&location=&project=&type=&job_hot_flag=&current={page_num}&limit=50"
                await page.goto(url, wait_until="networkidle")

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
            # Get job link
            link_el = await card.query_selector("a")
            href = await link_el.get_attribute("href") if link_el else ""

            # Extract job ID
            job_id = ""
            if href and "/position/" in href:
                parts = href.split("/position/")
                if len(parts) > 1:
                    job_id = parts[1].split("/")[0].split("?")[0]

            job_url = f"https://careers.tiktok.com{href}" if href and not href.startswith("http") else href

            # Get title
            title_el = await card.query_selector(".position-name, .job-title, h3, h4")
            title = await title_el.text_content() if title_el else ""

            # Get location
            location_el = await card.query_selector(".position-location, .job-location, [class*='location']")
            location = await location_el.text_content() if location_el else ""

            # Get department
            dept_el = await card.query_selector(".position-category, [class*='category']")
            department = await dept_el.text_content() if dept_el else ""

            return ScrapedJob(
                title=self.clean_text(title) or "",
                location=self.clean_text(location) or "",
                job_url=job_url,
                external_job_id=job_id,
                department=self.clean_text(department),
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job card: {e}")
            return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse raw job data (not used for Playwright scraper)."""
        return None
