"""GitHub - www.github.careers (iCIMS Jibe careers site, its own /api/jobs JSON).

careers-githubinc.icims.com redirects here; the jobs page reads
GET https://www.github.careers/api/jobs?page=N&limit=100. Verified 2026-10-20 (71 postings).
"""

from scrapers.base import ScraperConfig, ScraperType
from scrapers.custom._own_site import JibeMixin, OwnSiteScraper
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class GitHubScraper(JibeMixin, OwnSiteScraper):
    config = ScraperConfig(
        company_slug="github",
        company_name="GitHub",
        careers_url="https://www.github.careers/jobs",
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    BASE_URL = "https://www.github.careers"
