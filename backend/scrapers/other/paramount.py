"""Paramount job scraper - uses Playwright for SAP SuccessFactors."""

from scrapers.base import PlaywrightScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
import asyncio
import re


@ScraperRegistry.register(category="other")
class ParamountScraper(PlaywrightScraper):
    """Scraper for Paramount careers (SAP SuccessFactors - requires browser)."""

    config = ScraperConfig(
        company_slug="paramount",
        company_name="Paramount",
        careers_url="https://careers.paramount.com/search/",
        scraper_type=ScraperType.PLAYWRIGHT,
        rate_limit=10,
        max_pages=20,
        page_timeout=60,
    )

    BASE_URL = "https://careers.paramount.com/search/"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []

        page = await self.get_page()
        try:
            await page.goto(self.BASE_URL, wait_until="networkidle", timeout=45000)

            # Wait for job listings to load
            await asyncio.sleep(3)

            # Try to find job cards - SuccessFactors uses various selectors
            selectors = [
                'div[data-ph-at-id="job-card"]',
                'article.job-card',
                'div.jobs-list-item',
                'li[data-job-id]',
                'div.job-listing',
                'a[data-job-id]',
            ]

            job_elements = []
            for selector in selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    job_elements = await page.query_selector_all(selector)
                    if job_elements:
                        self.logger.info(f"Found {len(job_elements)} jobs with selector: {selector}")
                        break
                except:
                    continue

            if not job_elements:
                # Try extracting from page content
                content = await page.content()
                # Look for job data in JSON within the page
                jobs_data = self._extract_jobs_from_html(content)
                if jobs_data:
                    for job_data in jobs_data:
                        parsed = self._parse_extracted_job(job_data)
                        if parsed:
                            all_jobs.append(parsed)
            else:
                # Parse job elements
                for element in job_elements[:500]:  # Limit to 500 jobs
                    try:
                        parsed = await self._parse_job_element(element)
                        if parsed:
                            all_jobs.append(parsed)
                    except Exception as e:
                        self.logger.debug(f"Error parsing job element: {e}")
                        continue

            return ScrapeResult(
                success=True,
                jobs=all_jobs,
                jobs_found=len(all_jobs),
                error_message=None
            )

        except Exception as e:
            self.logger.error(f"Error scraping Paramount: {e}")
            return ScrapeResult(
                success=False,
                jobs=all_jobs,
                jobs_found=len(all_jobs),
                error_message=str(e)
            )
        finally:
            await page.close()

    def _extract_jobs_from_html(self, html: str) -> List[dict]:
        """Extract job data from HTML/JSON embedded in page."""
        jobs = []
        try:
            # Look for job data patterns in SuccessFactors pages
            # This is a fallback if DOM selectors don't work
            import json

            # Try to find JSON data in script tags
            json_pattern = r'jobList["\']?\s*[:=]\s*(\[[\s\S]*?\])'
            match = re.search(json_pattern, html)
            if match:
                try:
                    jobs = json.loads(match.group(1))
                except:
                    pass
        except:
            pass
        return jobs

    def _parse_extracted_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse job from extracted JSON data."""
        try:
            title = raw.get("title") or raw.get("jobTitle") or raw.get("name", "")
            job_id = str(raw.get("id") or raw.get("jobId") or raw.get("requisitionId", ""))
            location = raw.get("location") or raw.get("city", "")
            job_url = raw.get("url") or raw.get("applyUrl") or f"https://careers.paramount.com/job/{job_id}"

            if not title:
                return None

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=job_id,
                department=raw.get("department", ""),
            )
        except:
            return None

    async def _parse_job_element(self, element) -> Optional[ScrapedJob]:
        """Parse a job from a DOM element."""
        try:
            # Try various selectors for title
            title = ""
            title_selectors = ['h2', 'h3', '.job-title', '[data-ph-at-id="job-title"]', 'a']
            for sel in title_selectors:
                try:
                    title_el = await element.query_selector(sel)
                    if title_el:
                        title = await title_el.text_content()
                        if title:
                            break
                except:
                    continue

            if not title:
                return None

            # Try to get job URL
            job_url = ""
            try:
                link = await element.query_selector('a')
                if link:
                    job_url = await link.get_attribute('href')
                    if job_url and not job_url.startswith('http'):
                        job_url = f"https://careers.paramount.com{job_url}"
            except:
                pass

            # Try to get location
            location = ""
            location_selectors = ['.job-location', '[data-ph-at-id="job-location"]', '.location']
            for sel in location_selectors:
                try:
                    loc_el = await element.query_selector(sel)
                    if loc_el:
                        location = await loc_el.text_content()
                        if location:
                            break
                except:
                    continue

            # Extract job ID from URL or element
            job_id = ""
            if job_url:
                id_match = re.search(r'/job/(\d+)', job_url)
                if id_match:
                    job_id = id_match.group(1)

            if not job_id:
                try:
                    job_id = await element.get_attribute('data-job-id') or ""
                except:
                    pass

            return ScrapedJob(
                title=title.strip(),
                location=location.strip() if location else "",
                job_url=job_url or f"https://careers.paramount.com/search/",
                external_job_id=job_id,
            )
        except Exception as e:
            self.logger.debug(f"Error parsing job element: {e}")
            return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Required by base class."""
        return self._parse_extracted_job(raw)
