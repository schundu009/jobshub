"""The Muse job scraper — free public API, no auth required.

Provides 1000+ tech jobs from major companies.
API: https://www.themuse.com/api/public/jobs
Paginated, 20 per page, up to 50+ pages.
"""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="custom")
class TheMuseScraper(HTTPScraper):
    """Scraper for The Muse — free API, 1000+ tech jobs across major companies."""

    config = ScraperConfig(
        company_slug="themuse",
        company_name="The Muse",
        careers_url="https://www.themuse.com",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=20,  # 20 pages x 20 jobs = 400 jobs per category
    )

    API_URL = "https://www.themuse.com/api/public/jobs"

    # Scrape multiple engineering categories to maximize coverage
    CATEGORIES = [
        "Software Engineering",
        "Data and Analytics",
        "IT",
        "Design and UX",
        "Project and Product Management",
    ]

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        seen_ids = set()

        for category in self.CATEGORIES:
            page = 1
            while page <= self.config.max_pages:
                params = {
                    "category": category,
                    "location": "Flexible / Remote",
                    "page": page,
                }
                try:
                    data = await self.fetch_json(self.API_URL, params=params)
                except Exception:
                    break

                if not data:
                    break

                results = data.get("results", [])
                if not results:
                    break

                for job in results:
                    job_id = str(job.get("id", ""))
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    parsed = self.parse_job(job)
                    if parsed:
                        all_jobs.append(parsed)

                page_count = data.get("page_count", 1)
                if page >= page_count:
                    break
                page += 1

            # Also scrape US-based jobs
            page = 1
            while page <= 10:
                params = {
                    "category": category,
                    "location": "United States",
                    "page": page,
                }
                try:
                    data = await self.fetch_json(self.API_URL, params=params)
                except Exception:
                    break

                if not data:
                    break

                results = data.get("results", [])
                if not results:
                    break

                for job in results:
                    job_id = str(job.get("id", ""))
                    if job_id in seen_ids:
                        continue
                    seen_ids.add(job_id)
                    parsed = self.parse_job(job)
                    if parsed:
                        all_jobs.append(parsed)

                page_count = data.get("page_count", 1)
                if page >= page_count:
                    break
                page += 1

        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("name", "").strip()
            if not title:
                return None

            company_data = raw.get("company", {})
            company_name = company_data.get("name", "") if isinstance(company_data, dict) else ""

            locations = raw.get("locations", [])
            location = ", ".join([loc.get("name", "") for loc in locations]) if locations else "Remote"

            categories = raw.get("categories", [])
            department = categories[0].get("name", "") if categories else ""

            pub_date = raw.get("publication_date", "")
            posted_date = None
            if pub_date:
                try:
                    posted_date = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                except Exception:
                    pass

            levels = raw.get("levels", [])
            level_str = levels[0].get("name", "") if levels else ""

            refs = raw.get("refs", {})
            job_url = refs.get("landing_page", "") if isinstance(refs, dict) else ""

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=str(raw.get("id", "")),
                department=department,
                posted_date=posted_date,
                raw_data={"company_name": company_name},
            )
        except Exception as e:
            self.logger.error(f"Error parsing Muse job: {e}")
            return None
