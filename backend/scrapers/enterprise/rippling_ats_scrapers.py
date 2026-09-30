"""
Rippling ATS job boards (ats.rippling.com), pure HTTP.

Every board has a public JSON list at
    https://ats.rippling.com/api/v2/board/{board}/jobs?page=N&pageSize=M
returning {"items": [...], "page", "pageSize", "totalItems", "totalPages"}.
Pages are 0-based. A posting open in several locations appears once per
location (same "id"), so rows are merged by id. Each item carries name, url
(the public posting page), department.name and locations[] (name, city,
state, country, workplaceType). The list has no posting date.

Verified 2026-09-29.
"""

import asyncio
from typing import Dict, List, Optional

from scrapers.base import ScrapedJob, ScrapeResult, UnexpectedResponseError

_WORKPLACE_TYPES = {"REMOTE": "remote", "HYBRID": "hybrid", "ON_SITE": "on-site"}


class RipplingATSMixin:
    """Subclasses set BOARD (the slug in ats.rippling.com/{board}/jobs)."""

    BOARD: str = ""
    PAGE_SIZE = 500
    MAX_JOBS = 1500
    MAX_PAGES = 20
    # Celery soft-kills HTTP scrape tasks at 120s; stay well inside it.
    TIME_BUDGET_SECONDS = 60

    def board_api_url(self) -> str:
        return f"https://ats.rippling.com/api/v2/board/{self.BOARD}/jobs"

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS
        url = self.resolve_api_url(self.board_api_url())
        merged: Dict[str, dict] = {}
        page = 0
        pages_scraped = 0
        total_pages = None
        while page < self.MAX_PAGES:
            data = await self.fetch_json(url, params={"page": str(page), "pageSize": str(self.PAGE_SIZE)})
            items = self.expect_list(data, "items")
            pages_scraped += 1
            total_pages = data.get("totalPages")
            self.merge_items(merged, items)
            page += 1
            if not items or (total_pages is not None and page >= total_pages):
                break
            if len(merged) >= self.MAX_JOBS or loop.time() > deadline:
                self.logger.info(f"Rippling ATS: stopping at {len(merged)} jobs (cap/time budget)")
                break
            await asyncio.sleep(0.2)
        if pages_scraped == 1 and not merged and (data.get("totalItems") or 0) > 0:
            raise UnexpectedResponseError("totalItems > 0 but no items returned")
        jobs = self.parse_all(list(merged.values())[: self.MAX_JOBS])
        return ScrapeResult(
            success=True, jobs=jobs, jobs_found=len(jobs),
            pages_scraped=pages_scraped, total_pages=total_pages,
        )

    @staticmethod
    def merge_items(merged: Dict[str, dict], items: List[dict]) -> None:
        """Fold per-location duplicate rows into one posting with all locations."""
        for item in items:
            job_id = item.get("id")
            if not job_id:
                continue
            if job_id not in merged:
                merged[job_id] = {**item, "locations": list(item.get("locations") or [])}
                continue
            known = merged[job_id]["locations"]
            for loc in item.get("locations") or []:
                if loc not in known:
                    known.append(loc)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = (raw.get("name") or "").strip()
            job_id = raw.get("id")
            if not title or not job_id:
                return None
            locations = raw.get("locations") or []
            names = []
            for loc in locations:
                name = loc.get("name") or ", ".join(
                    p for p in (loc.get("city"), loc.get("state"), loc.get("country")) if p
                )
                if name and name not in names:
                    names.append(name)
            kinds = {_WORKPLACE_TYPES.get(loc.get("workplaceType")) for loc in locations} - {None}
            remote_type = next((k for k in ("remote", "hybrid", "on-site") if k in kinds), None)
            department = (raw.get("department") or {}).get("name")
            return ScrapedJob(
                title=title,
                location="; ".join(names),
                job_url=raw.get("url") or f"https://ats.rippling.com/{self.BOARD}/jobs/{job_id}",
                external_job_id=str(job_id),
                department=department or None,
                remote_type=remote_type,
                raw_data=raw,
            )
        except Exception as e:
            self.logger.error(f"Error parsing Rippling ATS job: {e}")
            return None
