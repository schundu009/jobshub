"""
Midjourney Jobs Scraper.

Uses Playwright for midjourney.com/careers.
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
class MidjourneyPlaywrightScraper(PlaywrightScraper):
    """Scraper for Midjourney careers."""

    config = ScraperConfig(
        company_slug="midjourney",
        company_name="Midjourney",
        careers_url="https://www.midjourney.com/careers/",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=5,
        page_timeout=60,
        max_pages=10,
    )

    BASE_URL = "https://www.midjourney.com/careers/"

    async def scrape(self) -> ScrapeResult:
        all_jobs = []
        page_num = 1

        page = await self.get_page()
        try:
            await page.goto(self.BASE_URL, wait_until="networkidle")
            await page.wait_for_timeout(5000)

            # Look for job listings
            try:
                await page.wait_for_selector(
                    "a[href*='/job'], a[href*='/careers/'], [class*='job'], [class*='position'], [class*='opening']",
                    timeout=15000
                )
            except:
                self.logger.info("Job list not found")

            # Get all job links - try various selectors
            cards = await page.query_selector_all(
                "a[href*='/job'], a[href*='/careers/'][href*='/'], [class*='job-card'] a, [class*='position'] a"
            )

            if not cards:
                # Try broader search
                cards = await page.query_selector_all("a[href*='careers']")

            self.logger.info(f"Found {len(cards)} potential job links")

            for card in cards:
                job = await self._parse_job_card(card)
                if job and job.external_job_id:
                    if not any(j.external_job_id == job.external_job_id for j in all_jobs):
                        all_jobs.append(job)

            # Try scrolling to load more
            for _ in range(3):
                prev_count = len(all_jobs)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

                new_cards = await page.query_selector_all("a[href*='/job'], a[href*='careers']")
                for card in new_cards:
                    job = await self._parse_job_card(card)
                    if job and job.external_job_id:
                        if not any(j.external_job_id == job.external_job_id for j in all_jobs):
                            all_jobs.append(job)

                if len(all_jobs) == prev_count:
                    break

            return ScrapeResult(success=True, jobs=all_jobs, pages_scraped=page_num)

        except Exception as e:
            self.logger.error(f"Error scraping Midjourney: {e}")
            return ScrapeResult(success=False, jobs=all_jobs, error_message=str(e))
        finally:
            await self.release_page(page)

    async def _parse_job_card(self, card) -> Optional[ScrapedJob]:
        try:
            href = await card.get_attribute("href")
            if not href:
                return None

            # Filter out non-job pages
            if '/careers' not in href and '/job' not in href:
                return None

            # Skip generic career pages
            if href.endswith('/careers') or href.endswith('/careers/'):
                return None

            job_id = ""
            match = re.search(r'/([a-z0-9-]+)/?$', href)
            if match:
                job_id = match.group(1)

            if not job_id or job_id in ['careers', 'jobs', 'about']:
                return None

            job_url = href if href.startswith("http") else f"https://www.midjourney.com{href}"

            title = await card.text_content()
            title = title.strip().split('\n')[0] if title else ""

            # Try to get title from child elements
            title_el = await card.query_selector("h2, h3, h4, [class*='title']")
            if title_el:
                title = await title_el.text_content()

            return ScrapedJob(
                title=self.clean_text(title) or f"Midjourney Position {job_id[:8]}",
                location="",
                job_url=job_url,
                external_job_id=job_id,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing: {e}")
            return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        return None
