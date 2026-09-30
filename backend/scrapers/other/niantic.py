"""
Niantic Jobs Scraper.

Niantic sold its games business (and nianticlabs.com/careers) to Scopely in
2025. The remaining company, Niantic Spatial, hires through Ashby
(jobs.ashbyhq.com/niantic-spatial, linked from nianticspatial.com/careers).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import AshbyMixin
from scrapers.registry import ScraperRegistry


# Moved to Ashby (verified 2026-09-29)
@ScraperRegistry.register(category="other")
class NianticScraper(AshbyMixin, HTTPScraper):
    """Scraper for Niantic (Niantic Spatial) careers."""

    config = ScraperConfig(
        company_slug="niantic",
        company_name="Niantic",
        careers_url="https://www.nianticspatial.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
    )

    API_URL = "https://api.ashbyhq.com/posting-api/job-board/niantic-spatial"
