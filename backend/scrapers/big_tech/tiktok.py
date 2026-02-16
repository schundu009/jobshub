"""
TikTok Jobs Scraper.

Uses Playwright for lifeattiktok.com/search (new careers portal).
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
class TikTokScraper(PlaywrightScraper):
    """Scraper for TikTok careers (lifeattiktok.com)."""

    config = ScraperConfig(
        company_slug="tiktok",
        company_name="TikTok",
        careers_url="https://lifeattiktok.com/search",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=10,
        page_timeout=60,
        max_pages=20,
    )

    BASE_URL = "https://lifeattiktok.com/search"

    async def scrape(self) -> ScrapeResult:
        """Scrape TikTok careers using Playwright."""
        all_jobs = []
        page_num = 1

        page = await self.get_page()
        try:
            # Navigate to jobs page
            await page.goto(self.BASE_URL, wait_until="networkidle")

            # Wait for the page to fully load
            await page.wait_for_timeout(3000)

            while page_num <= self.config.max_pages:
                # Wait for job cards to load
                try:
                    await page.wait_for_selector(
                        "[data-testid='job-card'], .job-card, [class*='JobCard'], [class*='job-item'], a[href*='/search/']",
                        timeout=15000
                    )
                except Exception:
                    self.logger.info(f"Job list not found on page {page_num}")
                    break

                # Get job cards - TikTok uses various card structures
                cards = await page.query_selector_all(
                    "[data-testid='job-card'], .job-card, [class*='JobCard'], [class*='job-item']"
                )

                # If no cards found with direct selectors, try finding job links
                if not cards:
                    cards = await page.query_selector_all("a[href*='/search/'][href*='7']")  # Job IDs start with 7

                if not cards:
                    self.logger.info(f"No job cards found on page {page_num}")
                    break

                self.logger.info(f"Found {len(cards)} job cards on page {page_num}")

                for card in cards:
                    job = await self._parse_job_card(card)
                    if job:
                        all_jobs.append(job)

                # Try to find and click next page
                # Look for pagination controls
                next_btn = await page.query_selector(
                    "button[aria-label='Next'], [class*='pagination'] button:last-child:not([disabled]), "
                    "[class*='next']:not([disabled]), a[rel='next']"
                )

                if not next_btn:
                    # Try scrolling to load more jobs (infinite scroll)
                    prev_count = len(all_jobs)
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await page.wait_for_timeout(2000)

                    # Check if more jobs loaded
                    new_cards = await page.query_selector_all(
                        "[data-testid='job-card'], .job-card, [class*='JobCard'], a[href*='/search/'][href*='7']"
                    )
                    if len(new_cards) <= len(cards):
                        break  # No more jobs to load

                    page_num += 1
                    continue

                # Click next button if found
                try:
                    await next_btn.click()
                    await page.wait_for_timeout(2000)
                    page_num += 1
                except Exception as e:
                    self.logger.warning(f"Could not click next page: {e}")
                    break

            # Deduplicate jobs by external_job_id
            seen_ids = set()
            unique_jobs = []
            for job in all_jobs:
                if job.external_job_id and job.external_job_id not in seen_ids:
                    seen_ids.add(job.external_job_id)
                    unique_jobs.append(job)

            return ScrapeResult(
                success=True,
                jobs=unique_jobs,
                pages_scraped=page_num,
            )

        except Exception as e:
            self.logger.error(f"Error scraping TikTok: {e}")
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
            # Get job link - could be the card itself or a child element
            tag_name = await card.evaluate("el => el.tagName.toLowerCase()")

            if tag_name == "a":
                href = await card.get_attribute("href")
                link_el = card
            else:
                link_el = await card.query_selector("a[href*='/search/']")
                href = await link_el.get_attribute("href") if link_el else ""

            if not href:
                return None

            # Extract job ID from URL like /search/7532194295143532807
            job_id = ""
            match = re.search(r'/search/(\d+)', href)
            if match:
                job_id = match.group(1)

            if not job_id:
                return None

            job_url = f"https://lifeattiktok.com{href}" if not href.startswith("http") else href

            # Get title - try various selectors
            title = ""
            title_selectors = [
                "h3", "h4", "[class*='title']", "[class*='Title']",
                "[class*='name']", "[class*='Name']", "span:first-child"
            ]
            for selector in title_selectors:
                title_el = await card.query_selector(selector)
                if title_el:
                    title = await title_el.text_content()
                    if title and len(title.strip()) > 3:
                        break

            # If still no title, get all text and take first meaningful part
            if not title:
                all_text = await card.text_content()
                if all_text:
                    # Take first line that looks like a job title
                    lines = [l.strip() for l in all_text.split('\n') if l.strip()]
                    for line in lines:
                        if len(line) > 5 and not line.startswith(('Show', 'Apply', 'Save')):
                            title = line
                            break

            # Get location
            location = ""
            location_selectors = [
                "[class*='location']", "[class*='Location']",
                "[class*='place']", "span:nth-child(2)"
            ]
            for selector in location_selectors:
                loc_el = await card.query_selector(selector)
                if loc_el:
                    location = await loc_el.text_content()
                    if location and len(location.strip()) > 2:
                        break

            # Get team/department
            department = ""
            dept_selectors = [
                "[class*='team']", "[class*='Team']",
                "[class*='category']", "[class*='department']"
            ]
            for selector in dept_selectors:
                dept_el = await card.query_selector(selector)
                if dept_el:
                    department = await dept_el.text_content()
                    if department and len(department.strip()) > 2:
                        break

            return ScrapedJob(
                title=self.clean_text(title) or f"TikTok Position {job_id[-6:]}",
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
