"""Remaining company scrapers - Greenhouse, Lever, Ashby, SmartRecruiters, Workday APIs."""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime, timedelta
import asyncio
import re


def _parse_workday_posted_on(text: str) -> Optional[datetime]:
    """
    Workday returns relative strings: "Posted Today", "Posted Yesterday",
    "Posted 3 Days Ago", "Posted 30+ Days Ago" (occasionally an ISO date).
    """
    if not text:
        return None
    t = text.strip().lower()
    now = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if "today" in t:
        return now
    if "yesterday" in t:
        return now - timedelta(days=1)
    m = re.search(r"(\d+)\+?\s*days?", t)
    if m:
        return now - timedelta(days=int(m.group(1)))
    try:
        return datetime.strptime(text.strip()[:10], "%Y-%m-%d")
    except ValueError:
        return None


# Helper mixin for Workday API parsing
class WorkdayMixin:
    # Celery kills HTTP scrape tasks at a 120s soft limit, and a killed task records
    # no ScraperRun (the scraper then shows as "never run"). Stay well inside it.
    MAX_JOBS = 1500
    TIME_BUDGET_SECONDS = 75
    # Public site root when it isn't https://{host}/{site} (e.g. myworkdaysite.com tenants)
    SITE_URL: Optional[str] = None

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 20  # Workday CXS rejects limit > 20 with HTTP 400
        deadline = asyncio.get_event_loop().time() + self.TIME_BUDGET_SECONDS
        while True:
            payload = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""}
            data = await self.fetch_json(self.API_URL, method="POST", json_data=payload)
            if not data:
                break
            jobs = self.expect_list(data, "jobPostings") if offset == 0 else (data.get("jobPostings") or [])
            if not jobs:
                break
            all_jobs.extend(self.parse_all(jobs))
            if len(jobs) < limit:
                break
            offset += limit
            if offset >= min(self.MAX_JOBS, 2000) or asyncio.get_event_loop().time() > deadline:
                self.logger.info(f"Workday: stopping at {len(all_jobs)} jobs (cap/time budget)")
                break
            await asyncio.sleep(0.05)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def _workday_site_url(self) -> str:
        """
        https://{host}/wday/cxs/{tenant}/{site}/jobs -> https://{host}/{site}

        Public job pages live at /{site}/job/...; keeping the tenant segment
        (/{tenant}/{site}/job/...) returns 404.
        """
        if self.SITE_URL:
            return self.SITE_URL.rstrip("/")
        head, _, tail = self.API_URL.partition("/wday/cxs/")
        parts = tail.split("/")
        site = parts[1] if len(parts) > 1 else parts[0]
        return f"{head}/{site}"

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            bullet = raw.get("bulletFields", [])
            external_path = raw.get("externalPath", "")
            # bulletFields[0] is the requisition id; fall back to the path's _R123 suffix
            job_id = bullet[0] if bullet else external_path.rsplit("_", 1)[-1]
            location = raw.get("locationsText", "")
            posted_date = _parse_workday_posted_on(raw.get("postedOn", ""))
            job_url = f"{self._workday_site_url()}{external_path}"
            return ScrapedJob(
                title=title, location=location, job_url=job_url, external_job_id=job_id,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing Workday job: {e}")
            return None


# Helper mixin for Greenhouse parsing
class GreenhouseMixin:
    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        # Honors ScraperConfigDB.config_overrides["url_override"] written by the
        # auto_heal_scrapers maintenance task (see BaseScraper.resolve_api_url).
        api_url = self.resolve_api_url(self.API_URL)
        data = await self.fetch_json(api_url, params={"content": "true"})
        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data")
        all_jobs = self.parse_all(self.expect_list(data, "jobs"))
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
                posted_date=posted
            )
        except:
            return None


class AshbyMixin:
    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        data = await self.fetch_json(self.API_URL)
        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data")
        # Unlisted Ashby postings are not publicly reachable
        raw_jobs = [j for j in self.expect_list(data, "jobs") if j.get("isListed", True)]
        all_jobs = self.parse_all(raw_jobs)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            pub = raw.get("publishedAt", "")
            posted = datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else None
            return ScrapedJob(
                title=raw.get("title", ""), location=raw.get("location") or "Remote",
                job_url=raw.get("jobUrl", ""), external_job_id=str(raw.get("id", "")),
                job_description=raw.get("descriptionHtml") or raw.get("descriptionPlain"),
                department=raw.get("department", ""), posted_date=posted,
                remote_type="remote" if raw.get("isRemote") else None,
            )
        except:
            return None


class LeverMixin:
    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        data = await self.fetch_json(self.API_URL)
        if data is None:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data")
        all_jobs = self.parse_all(self.expect_list(data))  # Lever returns a list directly
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            categories = raw.get("categories", {})
            location = categories.get("location", "")
            department = categories.get("department", "") or categories.get("team", "")
            created = raw.get("createdAt")
            posted = datetime.fromtimestamp(created / 1000) if created else None
            return ScrapedJob(
                title=raw.get("text", ""), location=location,
                job_url=raw.get("hostedUrl", ""), external_job_id=raw.get("id", ""),
                department=department, posted_date=posted
            )
        except:
            return None


class SmartRecruitersMixin:
    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 100
        while True:
            data = await self.fetch_json(self.API_URL, params={"offset": offset, "limit": limit})
            if not data:
                break
            jobs = self.expect_list(data, "content")
            if not jobs:
                break
            all_jobs.extend(self.parse_all(jobs))
            total = data.get("totalFound", 0)
            if len(jobs) < limit or offset + limit >= total:
                break
            offset += limit
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            loc = raw.get("location", {})
            city, region = loc.get("city", ""), loc.get("region", "")
            location = ", ".join([p for p in [city, region] if p]) or loc.get("country", "")
            if loc.get("remote"):
                location = f"{location} (Remote)" if location else "Remote"
            dept = raw.get("department", {})
            released = raw.get("releasedDate", "")
            posted = datetime.fromisoformat(released.replace("Z", "+00:00")) if released else None
            job_id = raw.get("id", "")
            return ScrapedJob(
                title=raw.get("name", ""), location=location,
                job_url=f"https://jobs.smartrecruiters.com/{self.COMPANY_ID}/{job_id}",
                external_job_id=raw.get("refNumber", "") or job_id,
                department=dept.get("label", "") if isinstance(dept, dict) else "",
                posted_date=posted
            )
        except:
            return None


# Greenhouse Scrapers
# Moved Greenhouse -> Ashby (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class OnePasswordScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="1password", company_name="1Password", careers_url="https://jobs.ashbyhq.com/1password", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/1password"

# Moved Greenhouse -> Ashby (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class AbridgeScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="abridge", company_name="Abridge", careers_url="https://jobs.ashbyhq.com/abridge", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/abridge"

@ScraperRegistry.register(category="custom")
class AgilentScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="agilent", company_name="Agilent", careers_url="https://agilent.wd5.myworkdayjobs.com/Agilent_Careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://agilent.wd5.myworkdayjobs.com/wday/cxs/agilent/Agilent_Careers/jobs"

@ScraperRegistry.register(category="custom")
class AnyscaleScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="anyscale", company_name="Anyscale", careers_url="https://jobs.ashbyhq.com/anyscale", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/anyscale"

@ScraperRegistry.register(category="custom")
class CharacterAIScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="characterai", company_name="Character AI", careers_url="https://jobs.ashbyhq.com/character", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/character"

@ScraperRegistry.register(category="custom")
class CircleCIScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="circleci", company_name="CircleCI", careers_url="https://circleci.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/circleci/jobs"

@ScraperRegistry.register(category="custom")
class CohereHealthScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="coherehealth", company_name="Cohere Health", careers_url="https://www.coherehealth.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/coherehealth/jobs"

# Moved Greenhouse -> Ashby (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class CrusoeEnergyScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="crusoeenergy", company_name="Crusoe Energy", careers_url="https://jobs.ashbyhq.com/crusoe", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/crusoe"

# Greenhouse board renamed latticehq -> lattice (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class LatticeScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="lattice", company_name="Lattice", careers_url="https://lattice.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/lattice/jobs"

# Moved Greenhouse -> Workday (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class MarvellScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="marvell", company_name="Marvell", careers_url="https://marvell.wd1.myworkdayjobs.com/MarvellCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://marvell.wd1.myworkdayjobs.com/wday/cxs/marvell/MarvellCareers/jobs"

# Moved Greenhouse -> Lever (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class MatchgroupScraper(LeverMixin, HTTPScraper):
    config = ScraperConfig(company_slug="matchgroup", company_name="Matchgroup", careers_url="https://jobs.lever.co/matchgroup", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.lever.co/v0/postings/matchgroup?mode=json"

@ScraperRegistry.register(category="custom")
class PlanetScaleScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="planetscale", company_name="PlanetScale", careers_url="https://planetscale.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/planetscale/jobs"

# Greenhouse board renamed pulumi -> pulumicorporation (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class PulumiScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pulumi", company_name="Pulumi", careers_url="https://www.pulumi.com/careers/", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/pulumicorporation/jobs"

# Moved Greenhouse -> Ashby (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class RenderScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="render", company_name="Render", careers_url="https://jobs.ashbyhq.com/render", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/render"

# Moved Greenhouse -> Ashby (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class RoboflowScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="roboflow", company_name="Roboflow", careers_url="https://jobs.ashbyhq.com/roboflow", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/roboflow"

@ScraperRegistry.register(category="custom")
class SambaNovaScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="sambanova", company_name="SambaNova", careers_url="https://sambanova.ai/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/sambanovasystems/jobs"

# Greenhouse board renamed sourcegraph -> sourcegraph91 (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class SourcegraphScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="sourcegraph", company_name="Sourcegraph", careers_url="https://sourcegraph.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/sourcegraph91/jobs"

# Moved Greenhouse -> Workday (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class TempusScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="tempus", company_name="Tempus", careers_url="https://tempus.wd5.myworkdayjobs.com/Tempus_Careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://tempus.wd5.myworkdayjobs.com/wday/cxs/tempus/Tempus_Careers/jobs"

# Moved Greenhouse -> Ashby (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class TemporalScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="temporal", company_name="Temporal", careers_url="https://jobs.ashbyhq.com/temporal", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/temporal"

# Moved Greenhouse (writerai) -> Ashby (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class WriterScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="writer", company_name="Writer", careers_url="https://jobs.ashbyhq.com/writer", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/writer"

# Moved Greenhouse (lambdalabs) -> Ashby (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class LambdaScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="lambda", company_name="Lambda", careers_url="https://jobs.ashbyhq.com/lambda", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/lambda"

# Moved Greenhouse (klatencor) -> Workday (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class KLAScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="kla", company_name="KLA", careers_url="https://kla.wd1.myworkdayjobs.com/Search", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://kla.wd1.myworkdayjobs.com/wday/cxs/kla/Search/jobs"

# board dead as of 2026-09-29; new ATS unknown
@ScraperRegistry.register(category="custom")
class AuroraScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="aurora", company_name="Aurora", careers_url="https://aurora.tech/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10, enabled=False, disabled_reason="board dead as of 2026-09-29; new ATS unknown")
    API_URL = "https://boards-api.greenhouse.io/v1/boards/auroradriver/jobs"

@ScraperRegistry.register(category="custom")
class ZscalerScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="zscaler", company_name="Zscaler", careers_url="https://zscaler.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/zscaler/jobs"


# Ashby Scrapers
# Cohere, Snowflake and Linear live in custom/cohere.py, custom/snowflake.py and
# custom/linear.py (one registration per slug).
@ScraperRegistry.register(category="custom")
class AxiomScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="axiom", company_name="Axiom", careers_url="https://axiom.co/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/axiom"

@ScraperRegistry.register(category="custom")
class BasetenScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="baseten", company_name="Baseten", careers_url="https://baseten.co/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/baseten"

@ScraperRegistry.register(category="custom")
class DecagonScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="decagon", company_name="Decagon", careers_url="https://decagon.ai/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/decagon"

@ScraperRegistry.register(category="custom")
class GenmoScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="genmo", company_name="Genmo", careers_url="https://genmo.ai/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/genmo"

@ScraperRegistry.register(category="custom")
class MintlifyScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="mintlify", company_name="Mintlify", careers_url="https://mintlify.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/mintlify"

@ScraperRegistry.register(category="custom")
class ModalScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="modal", company_name="Modal", careers_url="https://modal.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/modal"

@ScraperRegistry.register(category="custom")
class RelaceScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="relace", company_name="Relace", careers_url="https://relace.ai/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/relace"

@ScraperRegistry.register(category="custom")
class ResendScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="resend", company_name="Resend", careers_url="https://resend.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/resend"





# SmartRecruiters Scrapers
# API: https://api.smartrecruiters.com/v1/companies/{COMPANY_ID}/postings
@ScraperRegistry.register(category="custom")
class IntuitiveSurgicalScraper(SmartRecruitersMixin, HTTPScraper):
    config = ScraperConfig(company_slug="intuitivesurgical", company_name="Intuitive Surgical", careers_url="https://careers.intuitive.com/en/jobs/", scraper_type=ScraperType.HTTP, rate_limit=20, max_pages=50)
    API_URL = "https://api.smartrecruiters.com/v1/companies/Intuitive/postings"
    COMPANY_ID = "Intuitive"


# Lever Scrapers
# API: https://api.lever.co/v0/postings/{company}?mode=json
@ScraperRegistry.register(category="custom")
class RoScraper(LeverMixin, HTTPScraper):
    config = ScraperConfig(company_slug="ro", company_name="Ro", careers_url="https://jobs.lever.co/ro", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.lever.co/v0/postings/ro?mode=json"
