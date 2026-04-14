"""
HTTP scrapers for companies that were previously browser-only.
Converts Google, Snap, Meta, TikTok, ByteDance, NBCUniversal, Abbott,
Waymo, and others from Playwright to direct HTTP API calls.
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from scrapers.custom.remaining_scrapers import WorkdayMixin
from typing import List, Optional
from datetime import datetime
import asyncio
import json


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


# ─── Google (HTML scraper — custom careers site, no public API) ────────────
# Google careers uses a custom site with no JSON API.
# We scrape the NEXT_DATA from their SSR page.
@ScraperRegistry.register(category="big_tech")
class GoogleHTTPScraper(HTTPScraper):
    config = ScraperConfig(company_slug="google", company_name="Google", careers_url="https://www.google.com/about/careers/applications/jobs/results", scraper_type=ScraperType.HTTP, rate_limit=10, max_pages=20)

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        page = 1
        while page <= self.config.max_pages:
            url = f"https://www.google.com/about/careers/applications/jobs/results?page={page}&q=&location=United+States"
            html = await self.fetch_text(url)
            if not html:
                break

            # Extract job data from the HTML
            import re
            # Google embeds job data in the page as JSON
            matches = re.findall(r'"title":"([^"]+)"[^}]*"id":"([^"]+)"[^}]*"locations":\[([^\]]*)\]', html)
            if not matches:
                break

            for title, job_id, locs_raw in matches:
                locs = re.findall(r'"([^"]+)"', locs_raw)
                location = ", ".join(locs) if locs else ""
                all_jobs.append(ScrapedJob(
                    title=title,
                    location=location,
                    job_url=f"https://www.google.com/about/careers/applications/jobs/results/{job_id}",
                    external_job_id=job_id,
                ))

            if len(matches) < 20:
                break
            page += 1
            await asyncio.sleep(1)

        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        return None  # Parsing done inline in scrape()

    async def fetch_text(self, url: str) -> Optional[str]:
        """Fetch raw HTML text."""
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        return await resp.text()
        except Exception as e:
            self.logger.error(f"Fetch error: {e}")
        return None


# ─── Meta (Custom GraphQL — no public API, use search page scraping) ──────
@ScraperRegistry.register(category="big_tech")
class MetaHTTPScraper(HTTPScraper):
    config = ScraperConfig(company_slug="meta", company_name="Meta", careers_url="https://www.metacareers.com/jobs", scraper_type=ScraperType.HTTP, rate_limit=10, max_pages=20)

    async def scrape(self) -> ScrapeResult:
        # Meta's GraphQL API requires specific doc_ids that change.
        # Scrape the HTML search results page instead.
        all_jobs: List[ScrapedJob] = []
        page = 0
        while page < self.config.max_pages:
            url = f"https://www.metacareers.com/jobs?page={page}"
            html = await self.fetch_text(url)
            if not html:
                break

            import re
            # Meta embeds job data as JSON in the page
            matches = re.findall(r'"jobId":"(\d+)","title":"([^"]+)"[^}]*"location":"([^"]*)"', html)
            if not matches:
                # Try alternate pattern
                matches = re.findall(r'href="/v2/jobs/(\d+)/"[^>]*>([^<]+)</a>', html)

            if not matches:
                break

            for match in matches:
                if len(match) == 3:
                    job_id, title, location = match
                else:
                    job_id, title = match
                    location = ""
                all_jobs.append(ScrapedJob(
                    title=title, location=location,
                    job_url=f"https://www.metacareers.com/v2/jobs/{job_id}/",
                    external_job_id=job_id,
                ))

            if len(matches) < 10:
                break
            page += 1
            await asyncio.sleep(1)

        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        return None

    async def fetch_text(self, url: str) -> Optional[str]:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        return await resp.text()
        except Exception as e:
            self.logger.error(f"Fetch error: {e}")
        return None


# ─── TikTok / ByteDance (Custom API) ─────────────────────────────────────
@ScraperRegistry.register(category="big_tech")
class TikTokHTTPScraper(HTTPScraper):
    config = ScraperConfig(company_slug="tiktok", company_name="TikTok", careers_url="https://careers.tiktok.com", scraper_type=ScraperType.HTTP, rate_limit=20, max_pages=20)

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 20
        while offset < self.config.max_pages * limit:
            url = f"https://careers.tiktok.com/api/v1/search/job?keyword=&limit={limit}&offset={offset}&language=en"
            html = await self.fetch_text(url)
            if not html:
                break
            try:
                data = json.loads(html)
            except:
                break
            jobs = data.get("data", {}).get("job_list", [])
            if not jobs:
                break
            for job in jobs:
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)
            if len(jobs) < limit:
                break
            offset += limit
            await asyncio.sleep(0.5)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            job_id = str(raw.get("id", ""))
            location = raw.get("location", "")
            if isinstance(location, list):
                location = ", ".join(location)
            elif isinstance(location, dict):
                location = location.get("city", "")
            return ScrapedJob(
                title=title, location=location,
                job_url=f"https://careers.tiktok.com/position/{job_id}",
                external_job_id=job_id,
            )
        except Exception as e:
            self.logger.error(f"Error parsing TikTok job: {e}")
            return None

    async def fetch_text(self, url: str) -> Optional[str]:
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        return await resp.text()
        except Exception as e:
            self.logger.error(f"Fetch error: {e}")
        return None


@ScraperRegistry.register(category="big_tech")
class ByteDanceHTTPScraper(TikTokHTTPScraper):
    config = ScraperConfig(company_slug="bytedance", company_name="ByteDance", careers_url="https://jobs.bytedance.com", scraper_type=ScraperType.HTTP, rate_limit=20, max_pages=20)

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 20
        while offset < self.config.max_pages * limit:
            url = f"https://jobs.bytedance.com/api/v1/search/job?keyword=&limit={limit}&offset={offset}&language=en"
            html = await self.fetch_text(url)
            if not html:
                break
            try:
                data = json.loads(html)
            except:
                break
            jobs = data.get("data", {}).get("job_list", [])
            if not jobs:
                break
            for job in jobs:
                if parsed := self.parse_job(job):
                    all_jobs.append(parsed)
            if len(jobs) < limit:
                break
            offset += limit
            await asyncio.sleep(0.5)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            job_id = str(raw.get("id", ""))
            location = raw.get("location", "")
            if isinstance(location, list):
                location = ", ".join(location)
            elif isinstance(location, dict):
                location = location.get("city", "")
            return ScrapedJob(
                title=title, location=location,
                job_url=f"https://jobs.bytedance.com/position/{job_id}",
                external_job_id=job_id,
            )
        except:
            return None


# ─── Dynatrace (SmartRecruiters) ──────────────────────────────────────────
@ScraperRegistry.register(category="other")
class DynatraceHTTPScraper(HTTPScraper):
    config = ScraperConfig(company_slug="dynatrace", company_name="Dynatrace", careers_url="https://careers.dynatrace.com", scraper_type=ScraperType.HTTP, rate_limit=20, max_pages=20)
    API_URL = "https://careers.smartrecruiters.com/DynatraceAlliances"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        offset = 0
        while offset < 500:
            url = f"https://api.smartrecruiters.com/v1/companies/Dynatrace/postings?limit=100&offset={offset}"
            data = await self.fetch_json(url)
            if not data:
                break
            jobs = data.get("content", [])
            if not jobs:
                break
            for job in jobs:
                if parsed := self.parse_job(job):
                    all_jobs.append(parsed)
            if len(jobs) < 100:
                break
            offset += 100
            await asyncio.sleep(0.3)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("name", "")
            job_id = str(raw.get("id", raw.get("uuid", "")))
            loc = raw.get("location", {})
            location = f"{loc.get('city', '')}, {loc.get('region', '')}, {loc.get('country', '')}".strip(", ")
            posted = raw.get("releasedDate", "")
            posted_date = None
            if posted:
                try:
                    posted_date = datetime.fromisoformat(posted.replace("Z", "+00:00"))
                except:
                    pass
            department = raw.get("department", {}).get("label", "") if isinstance(raw.get("department"), dict) else ""
            return ScrapedJob(
                title=title, location=location,
                job_url=raw.get("ref", f"https://careers.smartrecruiters.com/Dynatrace/{job_id}"),
                external_job_id=job_id, department=department, posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing Dynatrace job: {e}")
            return None
