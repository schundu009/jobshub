"""
NetApp Jobs Scraper.

Uses Playwright for careers.netapp.com (Phenom People ATS).
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
class NetAppPhenomScraper(PlaywrightScraper):
    """Scraper for NetApp careers (Phenom People ATS)."""

    config = ScraperConfig(
        company_slug="netapp",
        company_name="NetApp",
        careers_url="https://careers.netapp.com/search-jobs",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=5,
        page_timeout=60,
        max_pages=30,
    )

    BASE_URL = "https://careers.netapp.com/search-jobs"

    async def scrape(self) -> ScrapeResult:
        """Scrape NetApp careers using Playwright."""
        all_jobs = []
        page_num = 1

        page = await self.get_page()
        try:
            # Navigate to jobs page
            await page.goto(self.BASE_URL, wait_until="networkidle")
            await page.wait_for_timeout(5000)

            while page_num <= self.config.max_pages:
                # Wait for job cards to load - Phenom uses various selectors
                try:
                    await page.wait_for_selector(
                        "[data-ph-id*='job'], .job-card, .job-tile, [class*='job-list'] a, .jobs-list a",
                        timeout=15000
                    )
                except Exception:
                    self.logger.info(f"Job list not found on page {page_num}")
                    break

                # Get job cards
                cards = await page.query_selector_all(
                    "[data-ph-id*='job-card'], .job-card, .job-tile, [class*='job-list'] li a, .jobs-list li a, a[href*='/job/']"
                )

                if not cards:
                    self.logger.info(f"No job cards found on page {page_num}")
                    break

                self.logger.info(f"Found {len(cards)} job cards on page {page_num}")
                initial_count = len(all_jobs)

                for card in cards:
                    job = await self._parse_job_card(card)
                    if job and job.external_job_id:
                        # Deduplicate
                        if not any(j.external_job_id == job.external_job_id for j in all_jobs):
                            all_jobs.append(job)

                # Try pagination or infinite scroll
                next_btn = await page.query_selector(
                    "button[aria-label='Next'], a[aria-label='Next'], "
                    "[class*='pagination'] [class*='next']:not([disabled]), "
                    "a[rel='next'], button:has-text('Next')"
                )

                if next_btn:
                    try:
                        await next_btn.click()
                        await page.wait_for_timeout(3000)
                        page_num += 1
                        continue
                    except Exception as e:
                        self.logger.warning(f"Could not click next: {e}")

                # Try infinite scroll
                prev_count = len(all_jobs)
                for _ in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)

                # Check if more jobs loaded
                new_cards = await page.query_selector_all(
                    "[data-ph-id*='job-card'], .job-card, .job-tile, a[href*='/job/']"
                )
                if len(new_cards) <= len(cards) and len(all_jobs) == prev_count:
                    break

                page_num += 1

            return ScrapeResult(
                success=True,
                jobs=all_jobs,
                pages_scraped=page_num,
            )

        except Exception as e:
            self.logger.error(f"Error scraping NetApp: {e}")
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
            tag_name = await card.evaluate("el => el.tagName.toLowerCase()")

            if tag_name == "a":
                href = await card.get_attribute("href")
            else:
                link_el = await card.query_selector("a[href*='/job/']")
                href = await link_el.get_attribute("href") if link_el else ""

            if not href:
                return None

            # Extract job ID from URL
            job_id = ""
            match = re.search(r'/job/([^/?\s]+)', href)
            if match:
                job_id = match.group(1)

            if not job_id:
                return None

            job_url = f"https://careers.netapp.com{href}" if not href.startswith("http") else href

            # Get title
            title = ""
            title_selectors = [
                "h2", "h3", "h4", "[class*='title']", "[class*='Title']",
                "[class*='job-name']", "[class*='job-title']", "span:first-child"
            ]
            for selector in title_selectors:
                title_el = await card.query_selector(selector)
                if title_el:
                    title = await title_el.text_content()
                    if title and len(title.strip()) > 3:
                        break

            if not title:
                all_text = await card.text_content()
                if all_text:
                    lines = [l.strip() for l in all_text.split('\n') if l.strip()]
                    for line in lines:
                        if len(line) > 5 and not line.startswith(('Show', 'Apply', 'Save', 'View')):
                            title = line
                            break

            # Get location
            location = ""
            location_selectors = [
                "[class*='location']", "[class*='Location']",
                "[class*='place']", "[class*='city']"
            ]
            for selector in location_selectors:
                loc_el = await card.query_selector(selector)
                if loc_el:
                    location = await loc_el.text_content()
                    if location and len(location.strip()) > 2:
                        break

            # Get department
            department = ""
            dept_selectors = [
                "[class*='team']", "[class*='Team']",
                "[class*='category']", "[class*='department']", "[class*='function']"
            ]
            for selector in dept_selectors:
                dept_el = await card.query_selector(selector)
                if dept_el:
                    department = await dept_el.text_content()
                    if department and len(department.strip()) > 2:
                        break

            return ScrapedJob(
                title=self.clean_text(title) or f"NetApp Position {job_id[:8]}",
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
