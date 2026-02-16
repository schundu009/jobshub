"""
Akamai Jobs Scraper.

Uses Playwright for jobs.akamai.com (Oracle Cloud HCM).
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
class AkamaiOracleScraper(PlaywrightScraper):
    """Scraper for Akamai careers (Oracle Cloud HCM)."""

    config = ScraperConfig(
        company_slug="akamai",
        company_name="Akamai",
        careers_url="https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=5,
        page_timeout=60,
        max_pages=30,
    )

    BASE_URL = "https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1/jobs"

    async def scrape(self) -> ScrapeResult:
        """Scrape Akamai careers using Playwright."""
        all_jobs = []
        page_num = 1

        page = await self.get_page()
        try:
            # Navigate to jobs page
            await page.goto(self.BASE_URL, wait_until="networkidle")
            await page.wait_for_timeout(5000)

            while page_num <= self.config.max_pages:
                # Wait for job list to load - Oracle HCM uses specific selectors
                try:
                    await page.wait_for_selector(
                        "[class*='job-list'] a, [class*='requisition'], a[href*='/job/'], a[href*='requisitionId']",
                        timeout=15000
                    )
                except Exception:
                    self.logger.info(f"Job list not found on page {page_num}")
                    break

                # Get job cards
                cards = await page.query_selector_all(
                    "a[href*='/job/'], a[href*='requisitionId'], [class*='job-card'] a, [class*='requisition-list'] a"
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
                    "button[aria-label='Next'], a[aria-label='Next page'], "
                    "[class*='pagination'] button:last-child:not([disabled])"
                )

                if next_btn:
                    is_disabled = await next_btn.get_attribute("disabled")
                    if not is_disabled:
                        try:
                            await next_btn.click()
                            await page.wait_for_timeout(3000)
                            page_num += 1
                            continue
                        except Exception as e:
                            self.logger.warning(f"Could not click next: {e}")

                # Try scrolling for infinite scroll
                prev_count = len(all_jobs)
                for _ in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)

                new_cards = await page.query_selector_all("a[href*='/job/'], a[href*='requisitionId']")
                if len(new_cards) <= len(cards) and len(all_jobs) == prev_count:
                    break

                page_num += 1

            return ScrapeResult(
                success=True,
                jobs=all_jobs,
                pages_scraped=page_num,
            )

        except Exception as e:
            self.logger.error(f"Error scraping Akamai: {e}")
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
            href = await card.get_attribute("href")

            if not href:
                return None

            # Extract job ID from URL
            job_id = ""
            match = re.search(r'requisitionId[=/](\d+)', href)
            if match:
                job_id = match.group(1)
            else:
                match = re.search(r'/job/(\d+)', href)
                if match:
                    job_id = match.group(1)

            if not job_id:
                return None

            job_url = href if href.startswith("http") else f"https://fa-extu-saasfaprod1.fa.ocs.oraclecloud.com{href}"

            # Get title
            title = ""
            title_el = await card.query_selector("h2, h3, [class*='title'], [class*='job-name']")
            if title_el:
                title = await title_el.text_content()
            else:
                title = await card.text_content()
                if title:
                    lines = [l.strip() for l in title.split('\n') if l.strip()]
                    title = lines[0] if lines else ""

            # Get location
            location = ""
            loc_el = await card.query_selector("[class*='location'], [class*='Location']")
            if loc_el:
                location = await loc_el.text_content()

            return ScrapedJob(
                title=self.clean_text(title) or f"Akamai Position {job_id}",
                location=self.clean_text(location) or "",
                job_url=job_url,
                external_job_id=job_id,
                department=None,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing job card: {e}")
            return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse raw job data (not used for Playwright scraper)."""
        return None
