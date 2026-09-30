"""
HTTP scrapers for companies that were previously browser-only.
Converts Google, Snap, Meta, TikTok, ByteDance, NBCUniversal, Abbott,
Waymo, and others from Playwright to direct HTTP API calls.
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult, UnexpectedResponseError
from scrapers.registry import ScraperRegistry
from scrapers.custom.remaining_scrapers import WorkdayMixin
from typing import List, Optional
from datetime import datetime
import asyncio
import json
import re


# ─── Abbott (Workday API — confirmed 2000+ jobs) ──────────────────────────
@ScraperRegistry.register(category="other")
class AbbottHTTPScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="abbott", company_name="Abbott", careers_url="https://www.jobs.abbott", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://abbott.wd5.myworkdayjobs.com/wday/cxs/abbott/abbottcareers/jobs"


# ─── Waymo (Greenhouse API — confirmed 373 jobs) ──────────────────────────
@ScraperRegistry.register(category="other")
class WaymoHTTPScraper(HTTPScraper):
    config = ScraperConfig(company_slug="waymo", company_name="Waymo", careers_url="https://waymo.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/waymo/jobs"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        data = await self.fetch_json(self.API_URL, params={"content": "true"})
        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data")
        for job in data.get("jobs", []):
            if parsed := self.parse_job(job):
                all_jobs.append(parsed)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            job_id = str(raw.get("id", ""))
            loc = raw.get("location", {})
            location = loc.get("name", "") if isinstance(loc, dict) else str(loc)
            updated = raw.get("updated_at", "")
            posted = datetime.fromisoformat(updated.replace("Z", "+00:00")) if updated else None
            depts = raw.get("departments", [])
            return ScrapedJob(
                title=raw.get("title", ""), location=location,
                job_url=raw.get("absolute_url", ""), external_job_id=job_id,
                job_description=raw.get("content", ""),
                department=depts[0].get("name", "") if depts else "",
                posted_date=posted,
            )
        except Exception as e:
            self.logger.error(f"Error parsing Waymo job: {e}")
            return None


# ─── Snap (Custom JSON API — confirmed 118+ jobs) ─────────────────────────
@ScraperRegistry.register(category="other")
class SnapHTTPScraper(HTTPScraper):
    config = ScraperConfig(company_slug="snap", company_name="Snap Inc.", careers_url="https://careers.snap.com", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://careers.snap.com/api/jobs"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        data = await self.fetch_json(self.API_URL, params={"limit": 500})
        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data")

        jobs = data.get("body", [])
        for job_wrapper in jobs:
            source = job_wrapper.get("_source", job_wrapper)
            if parsed := self.parse_job(source):
                all_jobs.append(parsed)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            job_id = raw.get("req_id", raw.get("Req_ID", ""))
            location = raw.get("location", "")
            if isinstance(location, list):
                location = ", ".join(location)
            job_url = raw.get("absolute_url", "")
            if not job_url and job_id:
                job_url = f"https://careers.snap.com/jobs/{job_id}"
            department = raw.get("team", raw.get("department", ""))
            description = raw.get("jobDescription", "")

            return ScrapedJob(
                title=title, location=location, job_url=job_url,
                external_job_id=str(job_id), department=department,
                job_description=description,
            )
        except Exception as e:
            self.logger.error(f"Error parsing Snap job: {e}")
            return None


# ─── Google (HTML page with embedded AF_initDataCallback JSON) ─────────────
# The results page server-renders 20 jobs per page into
# AF_initDataCallback({key: 'ds:1', ..., data: [[job, ...], None, total, page_size]}).
# Job record indexes: 0=id, 1=title, 3=[None, responsibilities html],
# 4=[None, qualifications html], 7=company, 9=[[location, ...], ...], 12=[created_secs, nanos].
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


@ScraperRegistry.register(category="big_tech")
class GoogleHTTPScraper(HTTPScraper):
    # 20 jobs/page; ~1s per page. 3 pages in flight keeps a full US crawl
    # (~90 pages) around 40s, well under the 120s Celery soft limit.
    config = ScraperConfig(company_slug="google", company_name="Google", careers_url="https://www.google.com/about/careers/applications/jobs/results", scraper_type=ScraperType.HTTP, rate_limit=10, max_pages=120)
    RESULTS_URL = "https://www.google.com/about/careers/applications/jobs/results"
    CONCURRENCY = 3
    _DS1 = re.compile(r"AF_initDataCallback\(\{key: 'ds:1', hash: '\d+', data:(.*?), sideChannel: \{\}\}\);", re.S)

    async def _page(self, page: int) -> tuple[list, int]:
        session = await self.get_session()
        params = {"location": "United States", "page": str(page)}
        async with session.get(self.RESULTS_URL, params=params, headers=_BROWSER_HEADERS) as resp:
            resp.raise_for_status()
            html = await resp.text()
        m = self._DS1.search(html)
        if not m:
            raise UnexpectedResponseError("Google results page has no ds:1 AF_initDataCallback block")
        data = json.loads(m.group(1))
        jobs = self.expect_list(data[0] if isinstance(data, list) and data else None)
        total = data[2] if len(data) > 2 and isinstance(data[2], int) else 0
        return jobs, total

    async def scrape(self) -> ScrapeResult:
        first, total = await self._page(1)
        raw_jobs = list(first)
        per_page = max(len(first), 1)
        last_page = min(self.config.max_pages, -(-total // per_page)) if total else 1
        sem = asyncio.Semaphore(self.CONCURRENCY)

        async def fetch(page: int) -> list:
            async with sem:
                try:
                    jobs, _ = await self._page(page)
                    return jobs
                except Exception as e:
                    self.logger.warning(f"Google page {page} failed: {e}")
                    return []

        for jobs in await asyncio.gather(*(fetch(p) for p in range(2, last_page + 1))):
            raw_jobs.extend(jobs)
        seen, unique = set(), []
        for job in self.parse_all(raw_jobs):
            if job.external_job_id not in seen:
                seen.add(job.external_job_id)
                unique.append(job)
        return ScrapeResult(success=True, jobs=unique, jobs_found=len(unique), pages_scraped=last_page, total_pages=last_page)

    def parse_job(self, raw: list) -> Optional[ScrapedJob]:
        try:
            job_id, title = str(raw[0]), raw[1]
            if not job_id or not title:
                return None
            locations = raw[9] or []
            location = "; ".join(loc[0] for loc in locations if loc and loc[0])
            desc = "".join(part[1] for part in (raw[3], raw[4]) if isinstance(part, list) and len(part) > 1 and part[1])
            created = raw[12] if len(raw) > 12 else None
            posted = datetime.utcfromtimestamp(created[0]) if isinstance(created, list) and created and created[0] else None
            return ScrapedJob(
                title=title, location=location,
                job_url=f"{self.RESULTS_URL}/{job_id}",
                external_job_id=job_id, job_description=desc or None, posted_date=posted,
            )
        except (IndexError, TypeError) as e:
            self.logger.debug(f"Error parsing Google job: {e}")
            return None


# ─── Meta ─────────────────────────────────────────────────────────────────
# Moved to Relay GraphQL over plain HTTP (verified 2026-09-29).
# metacareers.com/jobsearch/ loads every open role in ONE anonymous POST to
# /graphql (CareersJobSearchResultsV2DataQuery, ~1000 jobs, ~220KB). It needs
# the page's LSD token (one GET of /jobsearch/ first) and the query's doc_id.
# The doc_id changes when Meta redeploys; it lives in a static JS bundle as
# __d("CareersJobSearchResultsV2DataQuery_candidate_portalRelayOperation",...
# a.exports="<doc_id>"), so on a GraphQL error we re-discover it from the
# bundles the page references and retry once.
@ScraperRegistry.register(category="big_tech")
class MetaHTTPScraper(HTTPScraper):
    config = ScraperConfig(
        company_slug="meta", company_name="Meta", careers_url="https://www.metacareers.com/jobsearch",
        scraper_type=ScraperType.HTTP, rate_limit=10, max_pages=20, request_timeout=45,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-US,en;q=0.9",
        },
    )
    PAGE_URL = "https://www.metacareers.com/jobsearch/"
    GRAPHQL_URL = "https://www.metacareers.com/graphql"
    JOB_URL = "https://www.metacareers.com/profile/job_details/{id}/"
    QUERY_NAME = "CareersJobSearchResultsV2DataQuery"
    DOC_ID = "27129360303422352"  # verified 2026-09-29; re-discovered on failure
    MAX_JOBS = 1500
    MAX_BUNDLES = 25

    _LSD_RE = re.compile(r'"LSD",\[\],\{"token":"([^"]+)"')
    _BUNDLE_RE = re.compile(r'https://static\.xx\.fbcdn\.net/rsrc\.php/[^"\s]+?\.js')
    _DOC_ID_RE = re.compile(
        r'__d\("CareersJobSearchResultsV2DataQuery_[A-Za-z_]*RelayOperation",\[\],'
        r'\(function\([^)]*\)\{[a-z]\.exports="(\d+)"'
    )

    @staticmethod
    def search_variables() -> dict:
        return {
            "search_input": {
                "q": None, "divisions": [], "offices": [], "roles": [], "leadership_levels": [],
                "saved_jobs": [], "saved_searches": [], "sub_teams": [], "teams": [],
                "is_leadership": False, "is_remote_only": False, "sort_by_new": False,
                "results_per_page": None,
            },
            "viewasUserID": None,
            "isLoggedIn": False,
        }

    async def _get_text(self, url: str, headers: dict) -> str:
        session = await self.get_session()
        async with session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            return await resp.text()

    async def _query(self, lsd: str, doc_id: str) -> dict:
        form = {
            "av": "0", "__user": "0", "__a": "1", "lsd": lsd,
            "fb_api_caller_class": "RelayModern",
            "fb_api_req_friendly_name": self.QUERY_NAME,
            "variables": json.dumps(self.search_variables()),
            "doc_id": doc_id, "server_timestamps": "true",
        }
        headers = {
            "Accept": "*/*", "x-fb-lsd": lsd, "x-fb-friendly-name": self.QUERY_NAME,
            "Origin": "https://www.metacareers.com", "Referer": self.PAGE_URL,
            "sec-fetch-dest": "empty", "sec-fetch-mode": "cors", "sec-fetch-site": "same-origin",
        }
        session = await self.get_session()
        async with session.post(self.GRAPHQL_URL, data=form, headers=headers) as resp:
            resp.raise_for_status()
            text = await resp.text()
        # Relay may stream several JSON objects; the first carries the data.
        first = text.strip().split("\n", 1)[0]
        if first.startswith("for (;;);"):
            first = first[len("for (;;);"):]
        try:
            return json.loads(first)
        except ValueError:
            raise UnexpectedResponseError(f"Meta GraphQL returned non-JSON: {first[:120]!r}")

    async def _discover_doc_id(self, page_html: str) -> Optional[str]:
        bundles = list(dict.fromkeys(u.replace("\\/", "/") for u in self._BUNDLE_RE.findall(page_html)))
        for url in bundles[: self.MAX_BUNDLES]:
            try:
                js = await self._get_text(url, {"Accept": "*/*"})
            except Exception as e:
                self.logger.debug(f"Meta bundle fetch failed {url}: {e}")
                continue
            match = self._DOC_ID_RE.search(js)
            if match:
                return match.group(1)
        return None

    @staticmethod
    def _jobs_from(payload: dict) -> Optional[list]:
        data = (payload or {}).get("data") or {}
        result = data.get("job_search_with_featured_jobs_v2") or {}
        jobs = result.get("all_jobs")
        return jobs if isinstance(jobs, list) else None

    async def scrape(self) -> ScrapeResult:
        page_headers = {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "sec-fetch-dest": "document", "sec-fetch-mode": "navigate", "sec-fetch-site": "none",
        }
        html = await self._get_text(self.PAGE_URL, page_headers)
        lsd_match = self._LSD_RE.search(html)
        if not lsd_match:
            raise UnexpectedResponseError("metacareers.com page has no LSD token")
        lsd = lsd_match.group(1)

        jobs = self._jobs_from(await self._query(lsd, self.DOC_ID))
        if jobs is None:
            doc_id = await self._discover_doc_id(html)
            if not doc_id or doc_id == self.DOC_ID:
                raise UnexpectedResponseError("Meta GraphQL query failed and no new doc_id was found")
            self.logger.info(f"Meta: doc_id changed {self.DOC_ID} -> {doc_id}")
            jobs = self._jobs_from(await self._query(lsd, doc_id))
            if jobs is None:
                raise UnexpectedResponseError("Meta GraphQL returned no all_jobs list")

        parsed = self.parse_all(jobs[: self.MAX_JOBS]) if jobs else []
        return ScrapeResult(success=True, jobs=parsed, jobs_found=len(parsed), pages_scraped=1)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id = str(raw.get("id") or "")
        title = (raw.get("title") or "").strip()
        if not job_id or not title:
            return None
        locations = [loc for loc in (raw.get("locations") or []) if loc]
        teams = [t for t in (raw.get("teams") or []) if t]
        sub_teams = [t for t in (raw.get("sub_teams") or []) if t]
        department = " / ".join(filter(None, [teams[0] if teams else None, sub_teams[0] if sub_teams else None]))
        return ScrapedJob(
            title=title,
            location="; ".join(locations),
            job_url=self.JOB_URL.format(id=job_id),
            external_job_id=job_id,
            department=department or None,
            remote_type="remote" if locations and all("remote" in loc.lower() for loc in locations) else None,
        )


# ─── TikTok / ByteDance (ATSX public supplier API) ─────────────────────────
# Both career sites (lifeattiktok.com, joinbytedance.com) POST to
# /api/v1/public/supplier/search/job/posts; the "website-path" header picks
# the board. careers.tiktok.com and jobs.bytedance.com /api/v1/search/job now
# return an empty 200 body.
@ScraperRegistry.register(category="big_tech")
class TikTokHTTPScraper(HTTPScraper):
    config = ScraperConfig(company_slug="tiktok", company_name="TikTok", careers_url="https://lifeattiktok.com/search", scraper_type=ScraperType.HTTP, rate_limit=20, max_pages=60)
    API_URL = "https://api.lifeattiktok.com/api/v1/public/supplier/search/job/posts"
    WEBSITE_PATH = "tiktok"
    ORIGIN = "https://lifeattiktok.com"
    PAGE_SIZE = 100

    async def scrape(self) -> ScrapeResult:
        raw_jobs: list = []
        headers = {"website-path": self.WEBSITE_PATH, "origin": self.ORIGIN, "referer": f"{self.ORIGIN}/", "accept-language": "en-US"}
        offset, total = 0, None
        for _ in range(self.config.max_pages):
            body = {
                "recruitment_id_list": [], "job_category_id_list": [], "subject_id_list": [],
                "location_code_list": [], "keyword": "", "limit": self.PAGE_SIZE, "offset": offset,
            }
            data = await self.fetch_json(self.API_URL, method="POST", json_data=body, headers=headers)
            payload = data.get("data") if isinstance(data, dict) else None
            if not isinstance(payload, dict):
                raise UnexpectedResponseError(f"no 'data' object (code={data.get('code') if isinstance(data, dict) else '?'})")
            jobs = self.expect_list(payload, "job_post_list") if offset == 0 else (payload.get("job_post_list") or [])
            total = payload.get("count", total)
            raw_jobs.extend(jobs)
            offset += self.PAGE_SIZE
            if len(jobs) < self.PAGE_SIZE or (total is not None and offset >= total):
                break
            await asyncio.sleep(0.2)
        jobs = self.parse_all(raw_jobs)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=offset // self.PAGE_SIZE)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            job_id = str(raw.get("id") or "")
            title = raw.get("title") or ""
            if not job_id or not title:
                return None
            city = raw.get("city_info") or {}
            location = city.get("en_name") or city.get("i18n_name") or city.get("name") or ""
            category = raw.get("job_category") or {}
            desc = "\n\n".join(p for p in (raw.get("description"), raw.get("requirement")) if p)
            recruit = (raw.get("recruit_type") or {}).get("en_name") or None
            return ScrapedJob(
                title=title, location=location,
                job_url=f"{self.ORIGIN}/search/{job_id}",
                external_job_id=job_id,
                job_description=desc or None,
                department=category.get("en_name") or category.get("i18n_name") or "",
                employment_type=recruit,
            )
        except Exception as e:
            self.logger.error(f"Error parsing {self.config.company_name} job: {e}")
            return None


@ScraperRegistry.register(category="big_tech")
class ByteDanceHTTPScraper(TikTokHTTPScraper):
    config = ScraperConfig(company_slug="bytedance", company_name="ByteDance", careers_url="https://joinbytedance.com/search", scraper_type=ScraperType.HTTP, rate_limit=20, max_pages=60)
    API_URL = "https://jobs.bytedance.com/api/v1/public/supplier/search/job/posts"
    WEBSITE_PATH = "en"
    ORIGIN = "https://joinbytedance.com"


# ─── Dynatrace (Coveo search behind dynatrace.com/careers) ─────────────────
# SmartRecruiters "Dynatrace" board is empty; the careers site queries its own
# /api/coveo/search/ proxy (POST, returns every opening in one response).
@ScraperRegistry.register(category="other")
class DynatraceHTTPScraper(HTTPScraper):
    config = ScraperConfig(company_slug="dynatrace", company_name="Dynatrace", careers_url="https://www.dynatrace.com/careers/jobs/", scraper_type=ScraperType.HTTP, rate_limit=20, max_pages=1)
    API_URL = "https://www.dynatrace.com/api/coveo/search/"

    async def scrape(self) -> ScrapeResult:
        body = {"q": None, "numberOfResults": 1000, "wildcards": True, "facets": []}
        data = await self.fetch_json(self.API_URL, method="POST", json_data=body, headers={"Accept": "application/json"})
        jobs = self.parse_all(self.expect_list(data, "results"))
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=1)

    @staticmethod
    def _first(value) -> str:
        if isinstance(value, list):
            return ", ".join(str(v) for v in value if v)
        return str(value or "")

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            meta = raw.get("raw") or {}
            job_id = str(meta.get("id") or meta.get("job_id") or "")
            title = raw.get("title") or meta.get("title") or ""
            url = raw.get("clickUri") or meta.get("url") or ""
            if not job_id or not title or not url:
                return None
            location = ", ".join(p for p in (self._first(meta.get("office_locations")), self._first(meta.get("country"))) if p)
            flex = self._first(meta.get("flex_option")).lower()
            ts = meta.get("date")
            posted = datetime.utcfromtimestamp(int(ts) / 1000) if ts else None
            return ScrapedJob(
                title=title, location=location, job_url=url, external_job_id=job_id,
                job_description=meta.get("description") or None,
                department=self._first(meta.get("team")) or self._first(meta.get("division")),
                posted_date=posted,
                employment_type=self._first(meta.get("employment_type")) or None,
                remote_type="remote" if "remote" in flex else ("hybrid" if "hybrid" in flex else None),
            )
        except Exception as e:
            self.logger.error(f"Error parsing Dynatrace job: {e}")
            return None
