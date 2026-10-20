"""Elios AI - eliosai.com/browse-jobs (own JSON API).

The browse-jobs page reads GET https://api.eliosinsights.com/api/job-postings
(sorted by publishedAt desc; ~64 postings, rich-text body). Posting page:
https://eliosai.com/browse-jobs/<slug>. Elios staffs client teams, so some
postings are client placements. Verified 2026-10-20.
"""

from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, clean_location, parse_when
from scrapers.registry import ScraperRegistry

API_URL = "https://api.eliosinsights.com/api/job-postings"
COUNTRIES = {"US": "United States", "BR": "Brazil", "MX": "Mexico", "CO": "Colombia", "AR": "Argentina",
             "IN": "India", "CA": "Canada", "GB": "United Kingdom", "PH": "Philippines"}


def tiptap_text(node: Any) -> str:
    """Plain text (with line breaks and '- ' bullets) from a TipTap/ProseMirror doc."""
    if not isinstance(node, dict):
        return ""
    kind = node.get("type")
    if kind == "text":
        return node.get("text") or ""
    inner = "".join(tiptap_text(c) for c in node.get("content") or [])
    if kind == "listItem":
        return "- " + inner.strip() + "\n"
    if kind in ("paragraph", "heading"):
        return inner.strip() + "\n\n"
    return inner


@ScraperRegistry.register(category="custom")
class EliosAIScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="eliosai",
        company_name="Elios AI",
        careers_url="https://eliosai.com/browse-jobs",
        scraper_type=ScraperType.HTTP,
    )
    PAGE = 100

    def listing_items(self, payload: Any) -> list:
        return self.expect_list(self.expect_dict(payload), "data")

    async def fetch_raw(self) -> list:
        raw, offset = [], 0
        while True:
            data = await self.get_json(API_URL, params={
                "search": "", "sortBy.propertyPath": "publishedAt", "sortBy.entityName": "talentRequestPosting",
                "sortDirection": "DESC", "limit": self.PAGE, "offset": offset})
            items = self.listing_items(data)
            raw.extend(items)
            offset += len(items)
            if not items or not data.get("hasMore") or self.full(raw) or self.out_of_time():
                break
        return raw

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        loc = raw.get("location") or {}
        country = COUNTRIES.get(loc.get("country") or "", loc.get("country"))
        location = clean_location(loc.get("city"), loc.get("region"), country)
        workplace = (raw.get("workplaceType") or "").lower() or None
        if workplace == "remote":
            location = f"{location} (Remote)" if location else "Remote"
        lo, hi = raw.get("fromCompensation"), raw.get("toCompensation")
        return self.job(
            title=raw.get("title"),
            location=location,
            job_url=f"https://eliosai.com/browse-jobs/{raw.get('slug')}",
            external_job_id=raw.get("id"),
            job_description=tiptap_text(raw.get("details") or {}).strip() or None,
            posted_date=parse_when(raw.get("publishedAt") or raw.get("createdAt")),
            salary_min=int(float(lo)) if lo else None,
            salary_max=int(float(hi)) if hi else None,
            employment_type="contract" if raw.get("positionType") == "CONTRACT" else "full-time",
            employment_type_raw=raw.get("positionType"),
            remote_type={"remote": "remote", "hybrid": "hybrid", "on-site": "on-site"}.get(workplace or ""),
        )
