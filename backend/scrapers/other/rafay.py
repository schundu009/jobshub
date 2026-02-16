"""
Rafay Jobs Scraper.

Uses Playwright for rafay.co/company/careers.
"""

from typing import Optional
import re

from scrapers.base import (
    PlaywrightScraper,
    ScraperConfig,
    ScraperType,
    ScrapedJob,
    ScrapeResult,
)
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="other")
class RafayPlaywrightScraper(PlaywrightScraper):
    """Scraper for Rafay careers."""

    config = ScraperConfig(
        company_slug="rafay",
        company_name="Rafay",
        careers_url="https://rafay.co/company/careers",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=5,
        page_timeout=60,
        max_pages=10,
    )

    BASE_URL = "https://rafay.co/company/careers"

    async def scrape(self) -> ScrapeResult:
        all_jobs = []
        page_num = 1

        page = await self.get_page()
        try:
            await page.goto(self.BASE_URL, wait_until="networkidle")
            await page.wait_for_timeout(3000)

            # Get all job links
            cards = await page.query_selector_all("a[href*='/careers/']")

            self.logger.info(f"Found {len(cards)} potential job links")

            for card in cards:
                job = await self._parse_job_card(card)
                if job and job.external_job_id:
                    if not any(j.external_job_id == job.external_job_id for j in all_jobs):
                        all_jobs.append(job)

            return ScrapeResult(success=True, jobs=all_jobs, pages_scraped=page_num)

        except Exception as e:
            self.logger.error(f"Error scraping Rafay: {e}")
            return ScrapeResult(success=False, jobs=all_jobs, error_message=str(e))
        finally:
            await self.release_page(page)

    async def _parse_job_card(self, card) -> Optional[ScrapedJob]:
        try:
            href = await card.get_attribute("href")
            if not href:
                return None

            # Filter to job pages only
            if '/careers/' not in href:
                return None

            # Skip the main careers page
            if href.endswith('/careers') or href.endswith('/careers/'):
                return None

            # Extract job slug from URL like /careers/senior-software-engineer-india
            job_id = ""
            match = re.search(r'/careers/([a-z0-9-]+)/?$', href)
            if match:
                job_id = match.group(1)

            if not job_id:
                return None

            job_url = href if href.startswith("http") else f"https://rafay.co{href}"

            # Get title from the link text
            title = await card.text_content()
            title = title.strip() if title else ""

            # Try to get title from child elements
            title_el = await card.query_selector("h2, h3, h4, span, div")
            if title_el:
                title_text = await title_el.text_content()
                if title_text and title_text.strip():
                    title = title_text.strip()

            # Clean up the title - extract just the job name from slug if no title found
            if not title or title == "Apply Now":
                title = job_id.replace("-", " ").title()

            return ScrapedJob(
                title=self.clean_text(title),
                location="",
                job_url=job_url,
                external_job_id=job_id,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing: {e}")
            return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        return None
