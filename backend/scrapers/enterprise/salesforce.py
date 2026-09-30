"""
Salesforce Jobs Scraper.

Salesforce uses Workday for their careers site.
This scraper fetches from the Workday API and gets full job details.
"""

import asyncio
import re
from datetime import datetime, timedelta
from typing import Optional, List

from scrapers.base import (
    HTTPScraper,
    ScraperConfig,
    ScraperType,
    ScrapedJob,
    ScrapeResult,
)
from scrapers.registry import ScraperRegistry


def html_to_text(html: str) -> str:
    """Convert HTML to plain text."""
    if not html:
        return ""
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html)
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_posted_date(posted_text: str) -> Optional[datetime]:
    """Parse Workday posted date text like 'Posted Today', 'Posted 3 Days Ago'."""
    if not posted_text:
        return None

    text = posted_text.lower().strip()
    now = datetime.now()

    if 'today' in text:
        return now
    elif 'yesterday' in text:
        return now - timedelta(days=1)

    # "Posted X Days Ago"
    days_match = re.search(r'(\d+)\s*days?\s*ago', text)
    if days_match:
        days = int(days_match.group(1))
        return now - timedelta(days=days)

    # "Posted X+ Days Ago"
    days_match = re.search(r'(\d+)\+\s*days?\s*ago', text)
    if days_match:
        days = int(days_match.group(1))
        return now - timedelta(days=days)

    return None


def parse_salary_from_description(description: str) -> tuple:
    """Extract salary from job description."""
    if not description:
        return None, None

    # Remove HTML and normalize
    text = html_to_text(description).replace(',', '')

    # Patterns for salary
    patterns = [
        r'(\d{5,})\s*USD\s*[-–—to]+\s*(\d{5,})\s*USD',
        r'\$\s*(\d+)\s*[-–—to]+\s*\$?\s*(\d+)',
        r'salary\s*(?:range)?[:\s]*\$?\s*(\d{5,})\s*[-–—to]+\s*\$?\s*(\d{5,})',
        r'base\s*(?:pay|salary)[:\s]*\$?\s*(\d{5,})\s*[-–—to]+\s*\$?\s*(\d{5,})',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            min_val = int(match.group(1))
            max_val = int(match.group(2))
            # Validate reasonable range
            if 30000 <= min_val <= 1000000 and min_val <= max_val <= 2000000:
                return min_val, max_val

    return None, None


@ScraperRegistry.register(category="enterprise")
class SalesforceScraper(HTTPScraper):
    """Scraper for Salesforce careers using Workday API."""

    config = ScraperConfig(
        company_slug="salesforce",
        company_name="Salesforce",
        careers_url="https://careers.salesforce.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        page_size=20,
        max_pages=50,
    )

    BASE_URL = "https://salesforce.wd12.myworkdayjobs.com"
    API_URL = f"{BASE_URL}/wday/cxs/salesforce/External_Career_Site/jobs"

    async def scrape(self) -> ScrapeResult:
        """Scrape Salesforce careers via Workday API."""
        all_jobs: List[ScrapedJob] = []
        offset = 0
        page = 0

        while page < self.config.max_pages:
            try:
                # Fetch job listings
                payload = {
                    "appliedFacets": {},
                    "limit": self.config.page_size,
                    "offset": offset,
                    "searchText": ""
                }

                data = await self.fetch_json(
                    self.API_URL,
                    method="POST",
                    json_data=payload,
                    headers={"Content-Type": "application/json", "Accept": "application/json"}
                )

                job_postings = data.get("jobPostings", [])
                if not job_postings:
                    break

                # Fetch details for each job
                for job_data in job_postings:
                    external_path = job_data.get("externalPath", "")
                    if external_path:
                        job = await self._fetch_job_details(external_path, job_data)
                        if job:
                            all_jobs.append(job)
                        # Rate limit between detail fetches
                        await asyncio.sleep(0.3)

                # Check if more pages
                total = data.get("total", 0)
                offset += self.config.page_size
                if offset >= total:
                    break

                page += 1

            except Exception as e:
                self.logger.error(f"Error fetching page {page}: {e}")
                break

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            jobs_found=len(all_jobs),
            pages_scraped=page + 1,
        )

    async def _fetch_job_details(self, external_path: str, list_data: dict) -> Optional[ScrapedJob]:
        """Fetch full job details from detail API."""
        try:
            detail_url = f"{self.BASE_URL}/wday/cxs/salesforce/External_Career_Site{external_path}"

            detail = await self.fetch_json(
                detail_url,
                headers={"Accept": "application/json"}
            )

            job_info = detail.get("jobPostingInfo", {})

            # Keep the description HTML (like the Workday backfill and Greenhouse):
            # flattening it lost every heading and bullet the job page shows.
            description_html = job_info.get("jobDescription", "")
            description = description_html.strip() or None

            # Get posted date
            posted_text = job_info.get("postedOn", "") or list_data.get("postedOn", "")
            posted_date = parse_posted_date(posted_text)

            # If we have startDate, use that as a fallback
            if not posted_date:
                start_date = job_info.get("startDate", "")
                if start_date:
                    try:
                        posted_date = datetime.strptime(start_date, "%Y-%m-%d")
                    except ValueError:
                        pass

            # Extract salary from description
            salary_min, salary_max = parse_salary_from_description(description_html)

            # Build job URL
            job_url = job_info.get("externalUrl", "") or f"{self.BASE_URL}/External_Career_Site{external_path}"

            return ScrapedJob(
                title=job_info.get("title", "") or list_data.get("title", ""),
                location=job_info.get("location", "") or list_data.get("locationsText", ""),
                job_url=job_url,
                external_job_id=job_info.get("jobReqId", "") or job_info.get("id", ""),
                job_description=description,
                department=job_info.get("jobCategory", ""),
                posted_date=posted_date,
                salary_min=salary_min,
                salary_max=salary_max,
                raw_data=job_info,
            )

        except Exception as e:
            self.logger.warning(f"Error fetching job details for {external_path}: {e}")
            # Return basic info from list if detail fetch fails
            return ScrapedJob(
                title=list_data.get("title", ""),
                location=list_data.get("locationsText", ""),
                job_url=f"{self.BASE_URL}/External_Career_Site{external_path}",
                external_job_id=external_path.split("_")[-1] if "_" in external_path else "",
                posted_date=parse_posted_date(list_data.get("postedOn", "")),
            )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Not used - jobs are parsed in scrape method."""
        return None
