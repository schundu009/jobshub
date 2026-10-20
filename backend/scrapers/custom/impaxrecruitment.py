"""Impax Recruitment - www.impaxrecruitment.com/candidates (Webflow CMS; AI / Web3 recruiter).

The candidates page lists each role as div.job-cl-item (a.feature-single-title ->
/job/<slug>, work mode, work type, teaser). The list has no location, so each role's
own page (Location / Salary / Work Type fields + description) is read too - a dozen
pages, one a second. robots.txt is honoured. Verified 2026-10-20 (~11 roles).
"""

import re
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

LIST_URL = "https://www.impaxrecruitment.com/candidates"
LABELS = ("Company Name", "Location", "Salary", "Available Position", "Work Type", "Job Description")


def detail_fields(markup: str) -> dict:
    """Location / Salary / Work Type / description from a role page."""
    page = soup(markup)
    for t in page(["script", "style", "svg", "nav", "header", "footer"]):
        t.decompose()
    text = text_of(page)
    out = {}
    pattern = "(" + "|".join(re.escape(x) for x in LABELS) + ")"
    parts = re.split(pattern, text)
    for i in range(1, len(parts) - 1, 2):
        out.setdefault(parts[i], parts[i + 1].strip())
    return out


@ScraperRegistry.register(category="custom")
class ImpaxRecruitmentScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="impaxrecruitment",
        company_name="Impax Recruitment",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        allow_empty=True,
    )
    FETCH_DETAILS = True

    def listing_items(self, payload: Any) -> list:
        items, seen = [], set()
        for card in soup(payload).select("div.job-cl-item"):
            a = card.select_one("a.feature-single-title[href]") or card.find("a", href=re.compile(r"^/job/"))
            if not a:
                continue
            href = abs_url(LIST_URL, a["href"])
            if href in seen:
                continue
            seen.add(href)
            items.append({"href": href, "title": text_of(a), "mode": text_of(card.select_one(".feature-remote")),
                          "type": text_of(card.select_one(".feature-time")),
                          "teaser": text_of(card.select_one(".feature-single-detals"))})
        return items

    async def fetch_raw(self) -> list:
        items = self.listing_items(await self.get_text(LIST_URL))
        if self.FETCH_DETAILS:
            for item in items:
                if self.out_of_time():
                    break
                try:
                    item.update({f"d_{k}": v for k, v in detail_fields(await self.get_text(item["href"])).items()})
                except Exception as e:  # one bad page must not lose the list
                    self.logger.info(f"impax detail {item['href']}: {e}")
        return items

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        mode = raw.get("mode") or ""
        location = raw.get("d_Location") or ("Remote" if "remote" in mode.lower() else "")
        job = self.job(title=raw.get("title"), location=location, job_url=raw["href"],
                       external_job_id=raw["href"].rstrip("/").rsplit("/", 1)[-1],
                       job_description=raw.get("d_Job Description") or raw.get("teaser") or None,
                       employment_type_raw=raw.get("d_Work Type") or raw.get("type") or None,
                       remote_type="remote" if "remote" in mode.lower() else ("on-site" if "site" in mode.lower() else None))
        if job and raw.get("d_Salary"):
            job.extra["salary_text"] = raw["d_Salary"]
        return job
