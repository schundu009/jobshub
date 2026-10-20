"""Lumenalta - lumenalta.com/remote-jobs (own Next.js careers page; remote roles).

The remote-jobs page embeds its open roles in the page's React Server Component
payload ({"_id", "slug", "name", "skills", "seniority_level", ...}); each role's page
is https://lumenalta.com/jobs/<slug>. Every role is remote. robots.txt is honoured.
Verified 2026-10-20 (~10 roles).
"""

import json
import re
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper
from scrapers.registry import ScraperRegistry

LIST_URL = "https://lumenalta.com/remote-jobs"
_ROLE_RE = re.compile(r'\{"_id":"[0-9a-f]{24}","slug":"[^"]+".*?"seniority_level":(?:"[^"]*"|null)\}')


@ScraperRegistry.register(category="custom")
class LumenaltaScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="lumenalta",
        company_name="Lumenalta",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )

    def listing_items(self, payload: Any) -> list:
        text = (payload or "").replace('\\"', '"')
        items, seen = [], set()
        for m in _ROLE_RE.finditer(text):
            try:
                role = json.loads(m.group(0))
            except ValueError:
                continue
            if role.get("slug") and role["slug"] not in seen:
                seen.add(role["slug"])
                items.append(role)
        return items

    async def fetch_raw(self) -> list:
        return self.listing_items(await self.get_text(LIST_URL))

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job = self.job(title=raw.get("name"), location="Remote", job_url=f"https://lumenalta.com/jobs/{raw['slug']}",
                       external_job_id=raw.get("_id") or raw["slug"], remote_type="remote")
        if job and raw.get("skills"):
            job.extra["skills"] = [s for s in raw["skills"] if isinstance(s, str)][:20]
            job.extra["seniority"] = raw.get("seniority_level")
        return job
