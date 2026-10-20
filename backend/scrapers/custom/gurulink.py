"""GuruLink - www.gurulink.com/talent/browsejobs (Canadian tech recruiter; own RSS feed).

The browse-jobs page loads GET https://www.gurulink.com/proxy-api/rss, an RSS 2.0
feed "Job Openings at GuruLink Inc." with every opening (title, link, location,
job type and the full description in <description>). Posting page:
https://app.gurulink.ca/jobview.asp?JobID=<id> (the feed's own link). Verified 2026-10-20.
"""

import re
import xml.etree.ElementTree as ET
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType, UnexpectedResponseError
from scrapers.custom._own_site import OwnSiteScraper, parse_when, text_of
from scrapers.registry import ScraperRegistry

FEED_URL = "https://www.gurulink.com/proxy-api/rss"


@ScraperRegistry.register(category="custom")
class GuruLinkScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="gurulink",
        company_name="GuruLink",
        careers_url="https://www.gurulink.com/talent/browsejobs",
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )
    ROBOTS_FOR_HTML = False  # an RSS feed the page itself reads, not an HTML page

    def listing_items(self, payload: Any) -> list:
        if not isinstance(payload, str) or "<rss" not in payload[:500]:
            raise UnexpectedResponseError("GuruLink feed is not RSS")
        body = re.sub(r"^<\?xml[^>]*\?>", "", payload.strip())
        root = ET.fromstring(body)
        items = []
        for it in root.iter("item"):
            items.append({c.tag: (c.text or "").strip() for c in it})
        return items

    async def fetch_raw(self) -> list:
        return self.listing_items(await self._http("GET", FEED_URL, expect="text"))

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        link = raw.get("link") or raw.get("guid") or ""
        m = re.search(r"JobID=(\d+)", link, re.I)
        desc_html = raw.get("description") or ""
        loc = re.search(r"<b>Location:</b>\s*(.*?)<br", desc_html, re.I | re.S)
        jtype = re.search(r"<b>Job Type:</b>\s*(.*?)<br", desc_html, re.I | re.S)
        body = re.split(r"<b>Description:</b>", desc_html, maxsplit=1, flags=re.I)
        return self.job(
            title=raw.get("title"),
            location=text_of(loc.group(1)) if loc else "",
            job_url=link,
            external_job_id=m.group(1) if m else link,
            job_description=body[1] if len(body) > 1 else desc_html,
            posted_date=parse_when(raw.get("pubDate")),
            employment_type_raw=text_of(jtype.group(1)) if jtype else None,
            employment_type="contract" if jtype and "contract" in jtype.group(1).lower() else (
                "full-time" if jtype and "perm" in jtype.group(1).lower() else None),
        )
