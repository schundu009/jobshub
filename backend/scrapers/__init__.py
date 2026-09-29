"""
Custom Job Scraper System

Plugin-based architecture for scraping 58+ company career portals.
"""

from .base import (
    ScraperConfig,
    ScraperType,
    ScraperErrorType,
    UnexpectedResponseError,
    ScrapedJob,
    ScrapeResult,
    BaseScraper,
    HTTPScraper,
    PlaywrightScraper,
)
from .registry import ScraperRegistry

__all__ = [
    "ScraperConfig",
    "ScraperType",
    "ScraperErrorType",
    "UnexpectedResponseError",
    "ScrapedJob",
    "ScrapeResult",
    "BaseScraper",
    "HTTPScraper",
    "PlaywrightScraper",
    "ScraperRegistry",
]
