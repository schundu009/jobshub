"""Spotify job scraper - Lever API.

Spotify left Workday (ghr/Spotify now 404/422) for Lever board 'spotify'
(verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import LeverMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="custom")
class SpotifyScraper(LeverMixin, HTTPScraper):
    """Scraper for Spotify careers (Lever)."""

    config = ScraperConfig(
        company_slug="spotify",
        company_name="Spotify",
        careers_url="https://jobs.lever.co/spotify",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.lever.co/v0/postings/spotify?mode=json"
