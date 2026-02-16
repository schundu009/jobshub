"""
NBCUniversal Jobs Scraper.

Uses Playwright for nbcunicareers.com.
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
class NBCUniversalPlaywrightScraper(PlaywrightScraper):
    """Scraper for NBCUniversal careers."""

    config = ScraperConfig(
        company_slug="nbcuniversal",
        company_name="NBCUniversal",
        careers_url="https://www.nbcunicareers.com/careers",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=5,
        page_timeout=60,
        max_pages=50,
    )

    BASE_URL = "https://www.nbcunicareers.com/careers"

    async def scrape(self) -> ScrapeResult:
        all_jobs = []
        page_num = 1

        page = await self.get_page()
        try:
            await page.goto(self.BASE_URL, wait_until="networkidle")
            await page.wait_for_timeout(5000)

            while page_num <= self.config.max_pages:
                try:
                    await page.wait_for_selector(
                        "a[href*='/job/'], a[href*='/jobs/'], [class*='job-card'], [class*='job-list'] a",
                        timeout=15000
                    )
                except:
                    self.logger.info(f"Job list not found on page {page_num}")
                    break

                cards = await page.query_selector_all(
                    "a[href*='/job/'], a[href*='/jobs/'], [class*='job-card'] a"
                )

                if not cards:
                    break

                self.logger.info(f"Found {len(cards)} job cards on page {page_num}")

                for card in cards:
                    job = await self._parse_job_card(card)
                    if job and job.external_job_id:
                        if not any(j.external_job_id == job.external_job_id for j in all_jobs):
                            all_jobs.append(job)

                # Pagination
                next_btn = await page.query_selector(
                    "a[aria-label='Next'], button:has-text('Next'), [class*='pagination'] a.next"
                )
                if next_btn:
                    try:
                        await next_btn.click()
                        await page.wait_for_timeout(3000)
                        page_num += 1
                        continue
                    except:
                        pass

                # Try scroll
                prev_count = len(all_jobs)
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)
                if len(all_jobs) == prev_count:
                    break
                page_num += 1

            return ScrapeResult(success=True, jobs=all_jobs, pages_scraped=page_num)

        except Exception as e:
            self.logger.error(f"Error scraping NBCUniversal: {e}")
            return ScrapeResult(success=False, jobs=all_jobs, error_message=str(e))
        finally:
            await self.release_page(page)

    async def _parse_job_card(self, card) -> Optional[ScrapedJob]:
        try:
            href = await card.get_attribute("href")
            if not href or '/job' not in href.lower():
                return None

            job_id = ""
            match = re.search(r'/job[s]?/(\d+)', href)
            if match:
                job_id = match.group(1)
            else:
                match = re.search(r'/([a-z0-9-]+)/?$', href)
                if match:
                    job_id = match.group(1)
            if not job_id:
                return None

            job_url = href if href.startswith("http") else f"https://www.nbcunicareers.com{href}"

            title = ""
            title_el = await card.query_selector("h2, h3, h4, [class*='title']")
            if title_el:
                title = await title_el.text_content()
            if not title:
                title = await card.text_content()
                title = title.split('\n')[0].strip() if title else ""

            location = ""
            loc_el = await card.query_selector("[class*='location']")
            if loc_el:
                location = await loc_el.text_content()

            return ScrapedJob(
                title=self.clean_text(title) or f"NBCUniversal Position {job_id[:8]}",
                location=self.clean_text(location) or "",
                job_url=job_url,
                external_job_id=job_id,
            )
        except Exception as e:
            self.logger.warning(f"Error parsing: {e}")
            return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        return None
