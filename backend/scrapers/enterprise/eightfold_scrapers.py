"""
Eightfold AI career sites (HTTP only).

Eightfold serves two public JSON APIs, depending on the tenant's site generation:

- "apply/v2" (older sites, e.g. explore.jobs.netflix.net):
    GET /api/apply/v2/jobs?domain={domain}&start={n}&num=10
    -> {"count": int, "positions": [{id, name, location, locations, department,
        t_create, t_update, ats_job_id, display_job_id, work_location_option,
        canonicalPositionUrl, ...}]}
  (Sites on this generation answer {"message": "PCSX is not enabled ..."} to /api/pcsx/*.)

- "pcsx" (newer sites, e.g. jobs.vodafone.com):
    GET /api/pcsx/search?domain={domain}&query=&location=&start={n}
    -> {"status": 200, "data": {"count": int, "positions": [{id, displayJobId, name,
        location, locations, department, postedTs, creationTs, atsJobId,
        workLocationOption, positionUrl, ...}]}}
  (Sites on this generation answer {"message": "Not authorized for PCSX"} to /api/apply/v2/jobs.)

Both ignore larger page sizes and always return 10 positions per page, so pages
after the first are fetched concurrently. Descriptions are only exposed by
per-position endpoints (/api/apply/v2/jobs/{id}, /api/pcsx/position_details),
which would cost one request per job, so they are not fetched.
"""
import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from scrapers.base import HTTPScraper, ScrapedJob, ScraperConfig, ScraperType, ScrapeResult
from scrapers.registry import ScraperRegistry

_REMOTE_TYPES = {"remote": "remote", "hybrid": "hybrid", "onsite": "on-site", "on-site": "on-site"}


def _from_epoch(ts) -> Optional[datetime]:
    try:
        ts = int(ts)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).replace(tzinfo=None)


class EightfoldMixin:
    """
    Subclasses set SITE_URL (e.g. "https://jobs.vodafone.com"), DOMAIN
    (e.g. "vodafone.com") and API_VARIANT ("pcsx" or "apply_v2").
    """

    SITE_URL: str = ""
    DOMAIN: str = ""
    API_VARIANT: str = "apply_v2"
    PAGE_SIZE = 10  # Eightfold caps pages at 10 regardless of `num`
    CONCURRENCY = 6
    # Celery soft-limits HTTP scrape tasks at 120s; stay well inside it (see WorkdayMixin).
    MAX_JOBS = 1500
    TIME_BUDGET_SECONDS = 60

    # -- request helpers -------------------------------------------------------

    def _search_url(self) -> str:
        base = self.SITE_URL.rstrip("/")
        if self.API_VARIANT == "pcsx":
            return f"{base}/api/pcsx/search"
        return f"{base}/api/apply/v2/jobs"

    def _search_params(self, start: int) -> dict:
        params = {"domain": self.DOMAIN, "start": start}
        if self.API_VARIANT == "pcsx":
            params.update({"query": "", "location": ""})
        else:
            params["num"] = self.PAGE_SIZE
        return params

    def _unwrap(self, data) -> dict:
        """pcsx nests the payload under "data"; apply/v2 returns it at top level."""
        if self.API_VARIANT == "pcsx" and isinstance(data, dict) and isinstance(data.get("data"), dict):
            return data["data"]
        return data if isinstance(data, dict) else {}

    async def _fetch_page(self, start: int) -> list:
        data = await self.fetch_json(self._search_url(), params=self._search_params(start))
        return self._unwrap(data).get("positions") or []

    # -- scrape ----------------------------------------------------------------

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS

        first = await self.fetch_json(self._search_url(), params=self._search_params(0))
        if not first:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data")
        body = self._unwrap(first)
        if not body and isinstance(first, dict):
            body = first  # let expect_list report the real error keys (e.g. "message")
        raw_jobs: List[dict] = list(self.expect_list(body, "positions"))

        try:
            total = int(body.get("count") or 0)
        except (TypeError, ValueError):
            total = 0
        total = min(total, self.MAX_JOBS)

        starts = list(range(self.PAGE_SIZE, total, self.PAGE_SIZE)) if len(raw_jobs) >= self.PAGE_SIZE else []
        sem = asyncio.Semaphore(self.CONCURRENCY)

        async def fetch(start: int) -> list:
            if loop.time() > deadline:
                return []
            async with sem:
                if loop.time() > deadline:
                    return []
                try:
                    return await self._fetch_page(start)
                except Exception as e:  # one bad page shouldn't sink the whole board
                    self.logger.warning(f"Eightfold: page start={start} failed: {e}")
                    return []

        for page in await asyncio.gather(*(fetch(s) for s in starts)):
            raw_jobs.extend(page)
        if loop.time() > deadline:
            self.logger.info(f"Eightfold: time budget hit, keeping {len(raw_jobs)} of {total} positions")

        # Pages can shift while we paginate; dedupe by position id.
        seen = set()
        unique = []
        for raw in raw_jobs:
            key = raw.get("id") if isinstance(raw, dict) else None
            if key is None or key in seen:
                continue
            seen.add(key)
            unique.append(raw)

        jobs = self.parse_all(unique[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), error_message=None)

    # -- parse -----------------------------------------------------------------

    def _job_url(self, raw: dict) -> str:
        url = raw.get("canonicalPositionUrl") or raw.get("publicUrl") or raw.get("positionUrl") or ""
        if url.startswith("/"):
            url = f"{self.SITE_URL.rstrip('/')}{url}"
        if not url:
            url = f"{self.SITE_URL.rstrip('/')}/careers/job/{raw.get('id')}"
        return url

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            if not raw.get("id") or not (raw.get("name") or raw.get("posting_name")):
                return None
            pcsx = self.API_VARIANT == "pcsx"
            locations = [l for l in (raw.get("locations") or []) if l]
            primary = raw.get("location") or (locations[0] if locations else "")
            extra = [l for l in dict.fromkeys(locations) if l != primary]
            location = "; ".join([primary] + extra[:2]) if primary else "; ".join(extra[:3])

            if pcsx:
                posted = _from_epoch(raw.get("postedTs") or raw.get("creationTs"))
                ext_id = raw.get("displayJobId") or raw.get("atsJobId")
                wlo = raw.get("workLocationOption")
                desc = raw.get("jobDescription") or None
            else:
                posted = _from_epoch(raw.get("t_create") or raw.get("t_update"))
                ext_id = raw.get("display_job_id") or raw.get("ats_job_id")
                wlo = raw.get("work_location_option")
                desc = raw.get("job_description") or None

            return ScrapedJob(
                title=(raw.get("name") or raw.get("posting_name")).strip(),
                location=location or "",
                job_url=self._job_url(raw),
                external_job_id=str(ext_id or raw.get("id")),
                job_description=desc,
                department=raw.get("department") or None,
                posted_date=posted,
                # Some tenants tag "Remote, <country>" postings as onsite; trust the location.
                remote_type="remote" if "remote" in location.lower() else _REMOTE_TYPES.get(str(wlo or "").lower()),
            )
        except Exception as e:
            self.logger.error(f"Error parsing Eightfold job: {e}")
            return None


# Moved from Workday (netflix.wd1.myworkdayjobs.com) to Eightfold; verified 2026-09-29.
@ScraperRegistry.register(category="enterprise")
class NetflixEightfoldScraper(EightfoldMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="netflix",
        company_name="Netflix",
        careers_url="https://explore.jobs.netflix.net/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
    )
    SITE_URL = "https://explore.jobs.netflix.net"
    DOMAIN = "netflix.com"
    API_VARIANT = "apply_v2"
    API_URL = "https://explore.jobs.netflix.net/api/apply/v2/jobs?domain=netflix.com"


# Moved from Workday (vodafone.wd3.myworkdayjobs.com) to Eightfold PCSX; verified 2026-09-29.
@ScraperRegistry.register(category="enterprise")
class VodafoneEightfoldScraper(EightfoldMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="vodafone",
        company_name="Vodafone",
        careers_url="https://jobs.vodafone.com/careers",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
    )
    SITE_URL = "https://jobs.vodafone.com"
    DOMAIN = "vodafone.com"
    API_VARIANT = "pcsx"
    API_URL = "https://jobs.vodafone.com/api/pcsx/search?domain=vodafone.com"
