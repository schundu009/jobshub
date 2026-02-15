"""Palo Alto Networks job scraper - uses Workday API."""

import asyncio
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="other")
class PaloAltoNetworksScraper(HTTPScraper):
    """Scraper for Palo Alto Networks careers (Workday)."""

    config = ScraperConfig(
        company_slug="paloaltonetworks",
        company_name="Palo Alto Networks",
        careers_url="https://jobs.paloaltonetworks.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        max_pages=50,
    )

    API_URL = "https://paloaltonetworks.wd5.myworkdayjobs.com/wday/cxs/paloaltonetworks/panwexternalcareers/jobs"
    DETAIL_BASE = "https://paloaltonetworks.wd5.myworkdayjobs.com/wday/cxs/paloaltonetworks/panwexternalcareers"

    async def fetch_job_details(self, external_path: str) -> dict:
        """Fetch full job details from Workday API."""
        if not external_path:
            return {}
        try:
            detail_url = f"{self.DETAIL_BASE}{external_path}"
            return await self.fetch_json(detail_url) or {}
        except Exception:
            return {}

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 20

        while offset < self.config.max_pages * limit:
            payload = {
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": ""
            }

            data = await self.fetch_json(self.API_URL, method="POST", payload=payload)
            if not data:
                break

            job_postings = data.get("jobPostings", [])
            if not job_postings:
                break

            for job in job_postings:
                parsed = await self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

            total = data.get("total", 0)
            offset += limit
            if offset >= total:
                break

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            jobs_found=len(all_jobs),
            error_message=None
        )

    async def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            external_id = raw.get("bulletFields", [""])[0] if raw.get("bulletFields") else ""
            location = raw.get("locationsText", "")
            posted_on = raw.get("postedOn", "")
            job_path = raw.get("externalPath", "")

            # Fetch full job details for description
            job_description = ""
            department = ""
            details = await self.fetch_job_details(job_path)
            if details:
                job_info = details.get("jobPostingInfo", {})
                desc_html = job_info.get("jobDescription", "")
                if desc_html:
                    # Simple HTML to text conversion
                    import re
                    job_description = re.sub(r'<[^>]+>', ' ', desc_html)
                    job_description = re.sub(r'\s+', ' ', job_description).strip()
                department = job_info.get("jobCategory", "")
                # Get proper date from details
                if not posted_on or 'ago' in posted_on.lower():
                    posted_on = job_info.get("startDate") or job_info.get("postedOn", "")

            posted_date = None
            if posted_on and '-' in posted_on:
                try:
                    posted_date = datetime.strptime(posted_on, "%Y-%m-%dT%H:%M:%S.%f%z")
                except:
                    try:
                        posted_date = datetime.strptime(posted_on.split("T")[0], "%Y-%m-%d")
                    except:
                        pass

            job_url = f"https://paloaltonetworks.wd5.myworkdayjobs.com/en-US/panwexternalcareers{job_path}"

            # Rate limiting between job detail fetches
            await asyncio.sleep(0.1)

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=external_id or job_path,
                job_description=job_description[:10000] if job_description else "",
                department=department,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {e}")
            return None
