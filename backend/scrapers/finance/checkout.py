"""Checkout.com job scraper - Ashby API.

Moved Greenhouse -> Ashby board 'checkout.com' (verified 2026-09-29).
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import AshbyMixin
from scrapers.registry import ScraperRegistry


@ScraperRegistry.register(category="finance")
class CheckoutScraper(AshbyMixin, HTTPScraper):
    """Scraper for Checkout.com careers (Ashby)."""

    config = ScraperConfig(
        company_slug="checkout",
        company_name="Checkout.com",
        careers_url="https://www.checkout.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        max_pages=10,
    )

    API_URL = "https://api.ashbyhq.com/posting-api/job-board/checkout.com"
