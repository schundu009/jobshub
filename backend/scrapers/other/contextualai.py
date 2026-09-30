"""ContextualAI job scraper - uses Greenhouse API (migrated from Ashby)."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import GreenhouseMixin
from scrapers.registry import ScraperRegistry


# DISABLED: no public job board (verified 2026-09-29)
@ScraperRegistry.register(category="other")
class ContextualAIScraper(GreenhouseMixin, HTTPScraper):
    """Scraper for ContextualAI careers (Greenhouse)."""

    config = ScraperConfig(
        company_slug="contextualai",
        company_name="Contextual AI",
        careers_url="https://contextual.ai/careers/",
        scraper_type=ScraperType.HTTP,
        enabled=False,
        disabled_reason=(
            "No public job board as of 2026-09-29: contextual.ai/careers#open-roles lists no "
            "roles and references no ATS; Greenhouse/Ashby (incl. GraphQL)/Lever boards all 404"
        ),
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://boards-api.greenhouse.io/v1/boards/contextualai/jobs"
