"""
ARM Jobs Scraper.

Arm's applications run on iCIMS (experienced-arm.icims.com /
earlycareers-arm.icims.com), but the iCIMS job search is switched off and
redirects to careers.arm.com, a Radancy TalentBrew site that lists every
posting. So the jobs are read from the TalentBrew search endpoint.

careers.arm.com sends a ~9 KB Content-Security-Policy header, over aiohttp's
default 8190-byte header limit, so this scraper opens its session with a
larger max_field_size. Its result cards also differ from the stock
TalentBrew template: the title is the anchor text and location/category are
sibling <span>s in the card, so extract_items() fills those in.
"""

import ssl

import aiohttp
from bs4 import BeautifulSoup

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.enterprise.radancy_scrapers import RadancyMixin
from scrapers.registry import ScraperRegistry


# Moved to iCIMS behind a Radancy TalentBrew search site (verified 2026-09-29)
@ScraperRegistry.register(category="other")
class ARMScraper(RadancyMixin, HTTPScraper):
    """Scraper for ARM careers."""

    config = ScraperConfig(
        company_slug="arm",
        company_name="ARM",
        careers_url="https://careers.arm.com/search-jobs",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        request_timeout=30,
    )
    SITE_URL = "https://careers.arm.com"

    def extract_items(self, html: str) -> tuple:
        items, total_pages = super().extract_items(html)
        cards = {}
        for a in BeautifulSoup(html, "lxml").select("li a[data-job-id]"):
            card = a.find_parent("li")

            def text(cls, card=card):
                el = card.select_one(f".{cls}")
                return el.get_text(" ", strip=True) if el else ""

            cards[a["data-job-id"]] = {
                "title": " ".join(a.get_text(" ", strip=True).split()),
                "location": text("location"),
                "category": text("category"),
            }
        for item in items:
            for key, value in cards.get(item["job_id"], {}).items():
                if value and not item.get(key):
                    item[key] = value
        return items, total_pages

    async def get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/html, */*",
                "Accept-Language": "en-US,en;q=0.9",
                **self.config.headers,
            }
            ssl_context = ssl.create_default_context()
            try:
                import certifi
                ssl_context.load_verify_locations(certifi.where())
            except ImportError:
                pass
            kwargs = dict(
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self.config.request_timeout),
                connector=aiohttp.TCPConnector(ssl=ssl_context),
            )
            try:
                self._session = aiohttp.ClientSession(max_field_size=65536, **kwargs)
            except TypeError:  # aiohttp < 3.10 has no max_field_size
                self._session = aiohttp.ClientSession(**kwargs)
        return self._session
