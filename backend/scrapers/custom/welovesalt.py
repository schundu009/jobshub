"""Salt (welovesalt.com) - digital & tech recruiter; own job board, server-rendered HTML.

/jobs and /jobs/page/N list li.job-item entries (title link /jobs/<slug>-<id>,
location and category links, type / work-mode details), newest first; pages are
read until one adds nothing new. robots.txt is honoured. Verified 2026-10-20.
"""

import re
from typing import Any, Optional

from scrapers.base import ScrapedJob, ScraperConfig, ScraperType
from scrapers.custom._own_site import OwnSiteScraper, abs_url, soup, text_of
from scrapers.registry import ScraperRegistry

LIST_URL = "https://welovesalt.com/jobs"


@ScraperRegistry.register(category="custom")
class SaltScraper(OwnSiteScraper):
    config = ScraperConfig(
        company_slug="welovesalt",
        company_name="Salt",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
    )
    MAX_PAGES = 40

    def listing_items(self, payload: Any) -> list:
        items = []
        for li in soup(payload).select("li.job-item"):
            a = li.select_one(".job-item__title a[href]")
            if not a:
                continue
            highlights = li.select(".highlights__item")
            loc = cat = ""
            for h in highlights:
                icon = h.find("i") or {}
                cls = " ".join(icon.get("class", [])) if hasattr(icon, "get") else ""
                links = [text_of(x) for x in h.find_all("a")] or [text_of(h)]
                if "location" in cls:
                    loc = ", ".join(reversed(links))
                elif "star" in cls:
                    cat = ", ".join(links)
                elif "salary" in cls or "money" in cls:
                    pass
            details = [text_of(d) for d in li.select(".job-item__detail")]
            pay = next((text_of(h) for h in highlights if re.search(r"[£$€]\s*\d", text_of(h))), None)
            items.append({"href": abs_url(LIST_URL, a["href"]), "title": text_of(a), "location": loc,
                          "category": cat, "details": details, "pay": pay})
        return items

    async def fetch_raw(self) -> list:
        raw, seen = [], set()
        for page in range(1, self.MAX_PAGES + 1):
            url = LIST_URL if page == 1 else f"{LIST_URL}/page/{page}"
            html = await self.get_page_or_none(url)
            if html is None:
                break
            items = [i for i in self.listing_items(html) if i["href"] not in seen]
            if not items:
                break
            seen.update(i["href"] for i in items)
            raw.extend(items)
            if self.full(raw) or self.out_of_time():
                break
        else:
            self.truncated = True
        return raw

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        m = re.search(r"-(\d+)/?$", raw["href"])
        details = raw.get("details") or []
        etype = next((d for d in details if re.search(r"perm|temp|contract|freelance|fixed", d, re.I)), None)
        mode = next((d for d in details if re.search(r"remote|hybrid|office|site", d, re.I)), None)
        job = self.job(title=raw.get("title"), location=raw.get("location"), job_url=raw["href"],
                       external_job_id=m.group(1) if m else raw["href"], department=raw.get("category") or None,
                       employment_type_raw=etype,
                       employment_type="contract" if etype and re.search(r"temp|contract|freelance", etype, re.I) else (
                           "full-time" if etype and "perm" in etype.lower() else None),
                       remote_type=(mode or "").lower() or None)
        if job and raw.get("pay"):
            job.extra["salary_text"] = raw["pay"]
        return job
