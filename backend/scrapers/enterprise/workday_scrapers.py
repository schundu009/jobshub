"""Workday-based enterprise company scrapers using HTTP API."""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


class WorkdayAPIMixin:
    """Mixin for Workday job board scraping using HTTP API."""

    async def scrape(self) -> ScrapeResult:
        """Scrape Workday careers using their JSON API."""
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 50

        while True:
            payload = {"limit": limit, "offset": offset, "searchText": ""}

            try:
                data = await self.fetch_json(self.API_URL, method="POST", json=payload)
            except Exception as e:
                self.logger.error(f"Error fetching jobs from {self.API_URL}: {e}")
                if all_jobs:
                    # Return what we have so far
                    break
                return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message=str(e))

            if not data:
                self.logger.warning(f"No data returned from {self.API_URL}")
                break

            jobs = data.get("jobPostings", [])
            total = data.get("total", 0)

            if not jobs:
                if offset == 0:
                    self.logger.info(f"No jobs found for {self.config.company_name}")
                break

            for job in jobs:
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

            self.logger.debug(f"Fetched {len(jobs)} jobs (offset={offset}, total={total})")

            if len(jobs) < limit:
                break
            offset += limit
            if offset >= min(total, 1000):  # Cap at 1000 jobs
                break

        self.logger.info(f"Scraped {len(all_jobs)} jobs from {self.config.company_name}")
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse a job from Workday API response."""
        try:
            title = raw.get("title", "")
            if not title:
                return None

            # Extract job ID from bulletFields (usually first item)
            bullet_fields = raw.get("bulletFields", [])
            job_id = bullet_fields[0] if bullet_fields else ""

            # Location
            location = raw.get("locationsText", "")

            # Posted date
            posted_on = raw.get("postedOn", "")
            posted_date = None
            if posted_on:
                try:
                    posted_date = datetime.strptime(posted_on, "%Y-%m-%d")
                except:
                    pass

            # Build job URL from external path
            external_path = raw.get("externalPath", "")
            job_url = f"{self.BASE_URL}{external_path}" if external_path else ""

            return ScrapedJob(
                title=title.strip(),
                location=location.strip() if location else "",
                job_url=job_url,
                external_job_id=job_id,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.debug(f"Error parsing job: {e}")
            return None


# Company configurations: (slug, name, tenant, subdomain, job_site_path)
# Only companies with verified working Workday API endpoints (tested 2025-01)
# Many companies moved off Workday or have API protections requiring browser automation
WORKDAY_COMPANIES = [
    # Verified working with HTTP API - Total ~15,000+ jobs
    ("walmart", "Walmart", "walmart", "wd5", "WalmartExternal"),  # ~2000 jobs
    ("target", "Target", "target", "wd5", "targetcareers"),  # ~2000 jobs
    ("netflix", "Netflix", "netflix", "wd1", "Netflix"),  # ~800 jobs
    ("accenture", "Accenture", "accenture", "wd103", "AccentureCareers"),  # ~2000 jobs
    ("pwc", "PwC", "pwc", "wd3", "Global_Experienced_Careers"),  # ~4800 jobs
    ("deloitte", "Deloitte Ireland", "deloitteie", "wd3", "Experienced_Professionals"),  # ~45 jobs
    ("leidos", "Leidos", "leidos", "wd5", "External"),  # ~1600 jobs
    ("pnc", "PNC Bank", "pnc", "wd5", "External"),  # ~1400 jobs
    ("travelers", "Travelers", "travelers", "wd5", "External"),  # ~380 jobs
]


def create_workday_scraper(slug: str, name: str, tenant: str, subdomain: str, job_site_path: str):
    """Factory function to create Workday scraper classes using HTTP API."""
    base_url = f"https://{tenant}.{subdomain}.myworkdayjobs.com/{job_site_path}"
    api_url = f"https://{tenant}.{subdomain}.myworkdayjobs.com/wday/cxs/{tenant}/{job_site_path}/jobs"

    class WorkdayScraper(WorkdayAPIMixin, HTTPScraper):
        config = ScraperConfig(
            company_slug=slug,
            company_name=name,
            careers_url=base_url,
            scraper_type=ScraperType.HTTP,
            rate_limit=30,
            max_pages=20,
        )
        BASE_URL = base_url
        API_URL = api_url

    WorkdayScraper.__name__ = f"{slug.title().replace(' ', '')}Scraper"
    WorkdayScraper.__qualname__ = WorkdayScraper.__name__
    return WorkdayScraper


# Register all Workday scrapers
for company_config in WORKDAY_COMPANIES:
    slug, name, tenant, subdomain, job_site_path = company_config
    scraper_class = create_workday_scraper(slug, name, tenant, subdomain, job_site_path)
    ScraperRegistry.register(category="enterprise")(scraper_class)
