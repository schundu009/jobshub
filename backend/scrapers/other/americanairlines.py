"""
American Airlines Jobs Scraper.

Uses Playwright for jobs.aa.com (SAP SuccessFactors ATS).
"""

from datetime import datetime
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
class AmericanAirlinesSFScraper(PlaywrightScraper):
    """Scraper for American Airlines careers (SAP SuccessFactors)."""

    config = ScraperConfig(
        company_slug="americanairlines",
        company_name="American Airlines",
        careers_url="https://jobs.aa.com/search-jobs",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=5,
        page_timeout=60,
        max_pages=50,
    )

    BASE_URL = "https://jobs.aa.com/search-jobs"

    async def scrape(self) -> ScrapeResult:
        """Scrape American Airlines careers using Playwright."""
        all_jobs = []
        page_num = 1

        page = await self.get_page()
        try:
            # Navigate to jobs page
            await page.goto(self.BASE_URL, wait_until="networkidle")
            await page.wait_for_timeout(5000)

            while page_num <= self.config.max_pages:
                # Wait for job list to load - SuccessFactors uses specific selectors
                try:
                    await page.wait_for_selector(
                        "#search-results-list li, .search-results li, [class*='job-result'], a[href*='/job/']",
                        timeout=15000
                    )
                except Exception:
                    self.logger.info(f"Job list not found on page {page_num}")
                    break

                # Get job cards
                cards = await page.query_selector_all(
                    "#search-results-list li a[href*='/job/'], .search-results li a[href*='/job/'], a[href*='/job/']"
                )

                if not cards:
                    self.logger.info(f"No job cards found on page {page_num}")
                    break

                self.logger.info(f"Found {len(cards)} job cards on page {page_num}")

                for card in cards:
                    job = await self._parse_job_card(card)
                    if job and job.external_job_id:
                        # Deduplicate
                        if not any(j.external_job_id == job.external_job_id for j in all_jobs):
                            all_jobs.append(job)

                # Try pagination
                next_btn = await page.query_selector(
                    "a.next:not(.disabled), a[aria-label='Next'], "
                    "[class*='pagination'] a.next, button:has-text('Next')"
                )

                if next_btn:
                    is_disabled = await next_btn.get_attribute("class") or ""
                    if "disabled" not in is_disabled:
                        try:
                            await next_btn.click()
                            await page.wait_for_timeout(3000)
                            page_num += 1
                            continue
                        except Exception as e:
                            self.logger.warning(f"Could not click next: {e}")

                # Try scrolling
                prev_count = len(all_jobs)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

                new_cards = await page.query_selector_all("a[href*='/job/']")
                if len(new_cards) <= len(cards) and len(all_jobs) == prev_count:
                    break

                page_num += 1

            return ScrapeResult(
                success=True,
                jobs=all_jobs,
                pages_scraped=page_num,
            )

        except Exception as e:
            self.logger.error(f"Error scraping American Airlines: {e}")
            return ScrapeResult(
                success=False,
                jobs=all_jobs,
                error_message=str(e),
            )

        finally:
            await self.release_page(page)

    async def _parse_job_card(self, card) -> Optional[ScrapedJob]:
        """Parse a job card element."""
        try:
            # Get job link
            href = await card.get_attribute("href")

            if not href or '/job/' not in href:
                return None

            # Extract job ID from URL like /job/dallas/sr-developer/1097/78394839472
            job_id = ""
            match = re.search(r'/job/[^/]+/[^/]+/\d+/(\d+)', href)
            if match:
                job_id = match.group(1)
            else:
                # Try simpler pattern
                match = re.search(r'/(\d{8,})', href)
                if match:
                    job_id = match.group(1)

            if not job_id:
                return None

            job_url = f"https://jobs.aa.com{href}" if not href.startswith("http") else href

            # Get title from the link text or child elements
            title = ""
            title_el = await card.query_selector("h2, h3, .job-title, [class*='title']")
            if title_el:
                title = await title_el.text_content()
            else:
                title = await card.text_content()
                if title:
                    lines = [l.strip() for l in title.split('\n') if l.strip()]
                    title = lines[0] if lines else ""

            # Get parent li for more details
            parent = await card.evaluate("el => el.closest('li')")

            # Get location
            location = ""
            location_el = await card.query_selector("[class*='location'], .job-location")
            if location_el:
                location = await location_el.text_content()

            # Get department
            department = ""
            dept_el = await card.query_selector("[class*='category'], [class*='department']")
            if dept_el:
                department = await dept_el.text_content()

            return ScrapedJob(
                title=self.clean_text(title) or f"American Airlines Position {job_id[:8]}",
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
