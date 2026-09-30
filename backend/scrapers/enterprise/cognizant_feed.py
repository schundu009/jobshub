"""
Cognizant careers scraper (pure HTTP, no Playwright).

careers.cognizant.com pages sit behind a Cloudflare JS challenge (403 to plain
HTTP clients), but the site's job-board XML feed at /global-en/jobs/xml/?rss=true
is served without the challenge. It is an Indeed-style <source><job>...</job></source>
document holding every open posting (title, requisition id, public URL, city/
state/country, category, remote type, date, HTML description) in one ~11MB
response. Applications go to Taleo (cognizant.taleo.net). Verified 2026-09-29.
"""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional

from scrapers.base import (
    HTTPScraper,
    ScrapedJob,
    ScraperConfig,
    ScraperType,
    ScrapeResult,
    UnexpectedResponseError,
)
from scrapers.registry import ScraperRegistry


def _rfc822(value: Optional[str]) -> Optional[datetime]:
    """'Tue, 29 Sep 2026 19:32:11 GMT' -> naive UTC datetime."""
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@ScraperRegistry.register(category="enterprise")
class CognizantFeedScraper(HTTPScraper):
    config = ScraperConfig(
        company_slug="cognizant",
        company_name="Cognizant",
        careers_url="https://careers.cognizant.com/global-en/jobs/",
        scraper_type=ScraperType.HTTP,
        request_timeout=60,
    )
    API_URL = "https://careers.cognizant.com/global-en/jobs/xml/?rss=true"
    MAX_JOBS = 1500

    async def scrape(self) -> ScrapeResult:
        xml_text = await self.fetch_html(self.resolve_api_url(self.API_URL))
        raw_jobs = self.parse_feed(xml_text)[: self.MAX_JOBS]
        jobs = self.parse_all(raw_jobs)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), error_message=None)

    def parse_feed(self, xml_text: str) -> List[dict]:
        try:
            root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
        except ET.ParseError as e:
            raise UnexpectedResponseError(f"feed is not XML ({e}): {xml_text[:80]!r}")
        if root.tag != "source":
            raise UnexpectedResponseError(f"expected <source> job feed, got <{root.tag}>")
        return [{child.tag: (child.text or "").strip() for child in job} for job in root.iter("job")]

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title")
            url = raw.get("url")
            job_id = raw.get("requisitionid") or raw.get("referencenumber")
            if not (title and url and job_id):
                return None
            parts = [raw.get("city"), raw.get("state"), raw.get("country")]
            location = ", ".join(p for p in parts if p)
            remote = (raw.get("remotetype") or "").lower()
            remote_type = "hybrid" if "hybrid" in remote else ("remote" if "remote" in remote else None)
            jobtype = (raw.get("jobtype") or "").lower() or None
            return ScrapedJob(
                title=title,
                location=location,
                job_url=url,
                external_job_id=job_id,
                job_description=raw.get("description") or None,
                department=raw.get("category") or None,
                posted_date=_rfc822(raw.get("date")),
                employment_type=jobtype,
                remote_type=remote_type,
            )
        except Exception as e:
            self.logger.error(f"Error parsing Cognizant job: {e}")
            return None
