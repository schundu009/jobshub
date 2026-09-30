"""
Electronic Arts (EA) Jobs Scraper.

EA hires through an Avature portal at jobs.ea.com (server-rendered
SearchJobs pages, 20 jobs per page, jobOffset paging). EA's cards carry the
department in .list-item-department rather than the .list-item-family the
mixin reads, so _extract_rows() fills it in.
"""

from bs4 import BeautifulSoup

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.enterprise.avature_scrapers import _JOB_ID_RE, AvatureMixin
from scrapers.registry import ScraperRegistry


# Moved to Avature (verified 2026-09-29)
@ScraperRegistry.register(category="other")
class EAScraper(AvatureMixin, HTTPScraper):
    """Scraper for EA careers."""

    config = ScraperConfig(
        company_slug="ea",
        company_name="Electronic Arts",
        careers_url="https://jobs.ea.com/en_US/careers/SearchJobs",
        scraper_type=ScraperType.HTTP,
        rate_limit=15,
        request_timeout=20,
    )
    PORTAL_URL = "https://jobs.ea.com/en_US/careers"
    CONCURRENCY = 4

    def _extract_rows(self, html: str) -> list:
        rows = super()._extract_rows(html)
        departments = {}
        for card in BeautifulSoup(html, "lxml").select("article.article--result"):
            link = card.select_one("a[href*='JobDetail']")
            dept = card.select_one(".list-item-department")
            m = _JOB_ID_RE.search(link.get("href", "")) if link else None
            if m and dept:
                departments[m.group(1)] = " ".join(dept.get_text(" ", strip=True).split())
        for row in rows:
            if not row.get("department") and departments.get(row["id"]):
                row["department"] = departments[row["id"]]
        return rows
