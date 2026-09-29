"""Mistral AI job scraper - Ashby API.

Lever board emptied; moved to Ashby board 'mistral.ai' (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import AshbyMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class MistralAIScraper(AshbyMixin, HTTPScraper):
    """Scraper for Mistral AI careers (Ashby)."""

    config = ScraperConfig(
        company_slug="mistralai",
        company_name="Mistral AI",
        careers_url="https://mistral.ai/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.ashbyhq.com/posting-api/job-board/mistral.ai"
