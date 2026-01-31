"""Pfizer job scraper - Custom careers site."""

from scrapers.base import PlaywrightScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime
import asyncio
import re


@ScraperRegistry.register(category="custom")
class PfizerScraper(PlaywrightScraper):
    """Scraper for Pfizer careers at pfizer.com."""

    config = ScraperConfig(
        company_slug="pfizer",
        company_name="Pfizer",
        careers_url="https://www.pfizer.com/about/careers/search-results",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=10,
        max_pages=10,
        page_timeout=45,
    )

    BASE_URL = "https://www.pfizer.com/about/careers/search-results"

    async def scrape(self) -> ScrapeResult:
        """Scrape Pfizer careers page."""
        all_jobs: List[ScrapedJob] = []
        page = await self.get_page()

        try:
            # Navigate with pagination params
            url = f"{self.BASE_URL}?langcode=en&count=100&sort=latest"
            await page.goto(url, wait_until="domcontentloaded", timeout=30000)

            # Wait for job listings to load
            await asyncio.sleep(3)

            # Try various selectors for job listings
            job_selectors = [
                '.careers-search-results__item',
                '.views-row',
                'article.node--type-job',
                '[class*="job-listing"]',
                '.career-item',
                'li[class*="careers"]',
            ]

            job_elements = []
            for selector in job_selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    job_elements = await page.query_selector_all(selector)
                    if job_elements:
                        self.logger.info(f"Found {len(job_elements)} jobs with selector: {selector}")
                        break
                except:
                    continue

            if not job_elements:
                # Try scrolling to trigger lazy loading
                for _ in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)

                # Try again with broader selector
                job_elements = await page.query_selector_all('a[href*="/careers/"]')

            for element in job_elements[:100]:
                job = await self._parse_job_element(element)
                if job:
                    all_jobs.append(job)

            self.logger.info(f"Scraped {len(all_jobs)} jobs from Pfizer")
            return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

        except Exception as e:
            self.logger.error(f"Error scraping Pfizer: {e}")
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message=str(e))
        finally:
            await self.release_page(page)

    async def _parse_job_element(self, element) -> Optional[ScrapedJob]:
        """Parse a job element from the page."""
        try:
            # Try to get title
            title = ""
            title_selectors = ['h3 a', 'h2 a', 'a.title', '.title a', 'a[href*="/job/"]', 'a']
            for sel in title_selectors:
                title_el = await element.query_selector(sel)
                if title_el:
                    title = await title_el.text_content()
                    href = await title_el.get_attribute("href")
                    if title and href:
                        break

            if not title or len(title.strip()) < 3:
                return None

            # Build job URL
            job_url = ""
            if href:
                if href.startswith("http"):
                    job_url = href
                else:
                    job_url = f"https://www.pfizer.com{href}"

            # Try to get location
            location = ""
            location_selectors = ['.location', '[class*="location"]', '.field--name-field-location']
            for sel in location_selectors:
                loc_el = await element.query_selector(sel)
                if loc_el:
                    location = await loc_el.text_content()
                    if location:
                        break

            return ScrapedJob(
                title=title.strip(),
                location=location.strip() if location else "",
                job_url=job_url,
                external_job_id="",
            )
        except Exception as e:
            self.logger.debug(f"Error parsing job element: {e}")
            return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Not used for Playwright scraper."""
        return None
