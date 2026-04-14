"""Remaining company scrapers - Greenhouse, Lever, Ashby, SmartRecruiters, Workday APIs."""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime
import asyncio


# Helper mixin for Workday API parsing
class WorkdayMixin:
    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 50
        while True:
            payload = {"limit": limit, "offset": offset, "searchText": ""}
            data = await self.fetch_json(self.API_URL, method="POST", json=payload)
            if not data:
                break
            jobs = data.get("jobPostings", [])
            if not jobs:
                break
            for job in jobs:
                if parsed := self.parse_job(job):
                    all_jobs.append(parsed)
            if len(jobs) < limit:
                break
            offset += limit
            if offset >= 2000:
                break
            await asyncio.sleep(0.2)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            bullet = raw.get("bulletFields", [])
            job_id = bullet[0] if bullet else ""
            location = raw.get("locationsText", "")
            posted_on = raw.get("postedOn", "")
            posted_date = datetime.strptime(posted_on, "%Y-%m-%d") if posted_on else None
            external_path = raw.get("externalPath", "")
            # Derive job URL from API_URL by removing /wday/cxs/ prefix
            base = self.API_URL.replace("/wday/cxs/", "/").rsplit("/jobs", 1)[0]
            job_url = f"{base}{external_path}"
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
        for job in data.get("jobs", []):
            if parsed := self.parse_job(job):
                all_jobs.append(parsed)
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            pub = raw.get("publishedAt", "")
            posted = datetime.fromisoformat(pub.replace("Z", "+00:00")) if pub else None
            return ScrapedJob(
                title=raw.get("title", ""), location=raw.get("location", "Remote"),
                job_url=raw.get("jobUrl", ""), external_job_id=str(raw.get("id", "")),
                department=raw.get("department", ""), posted_date=posted
            )
        except:
            return None


class LeverMixin:
    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        data = await self.fetch_json(self.API_URL)
        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data")
        for job in data:  # Lever returns a list directly
            if parsed := self.parse_job(job):
                all_jobs.append(parsed)
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
            jobs = data.get("content", [])
            if not jobs:
                break
            for job in jobs:
                if parsed := self.parse_job(job):
                    all_jobs.append(parsed)
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
@ScraperRegistry.register(category="custom")
class OnePasswordScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="1password", company_name="1Password", careers_url="https://1password.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/1password/jobs"

@ScraperRegistry.register(category="custom")
class AbridgeScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="abridge", company_name="Abridge", careers_url="https://abridge.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/abridge/jobs"

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

@ScraperRegistry.register(category="custom")
class CrusoeEnergyScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="crusoeenergy", company_name="Crusoe Energy", careers_url="https://crusoe.ai/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/crusoe/jobs"

@ScraperRegistry.register(category="custom")
class LatticeScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="lattice", company_name="Lattice", careers_url="https://lattice.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/latticehq/jobs"

@ScraperRegistry.register(category="custom")
class MarvellScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="marvell", company_name="Marvell", careers_url="https://marvell.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/marvell/jobs"

@ScraperRegistry.register(category="custom")
class MatchgroupScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="matchgroup", company_name="Matchgroup", careers_url="https://matchgroup.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/match/jobs"

@ScraperRegistry.register(category="custom")
class PlanetScaleScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="planetscale", company_name="PlanetScale", careers_url="https://planetscale.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/planetscale/jobs"

@ScraperRegistry.register(category="custom")
class PulumiScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pulumi", company_name="Pulumi", careers_url="https://pulumi.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/pulumi/jobs"

@ScraperRegistry.register(category="custom")
class RenderScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="render", company_name="Render", careers_url="https://render.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/render/jobs"

@ScraperRegistry.register(category="custom")
class RoboflowScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="roboflow", company_name="Roboflow", careers_url="https://roboflow.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/roboflow/jobs"

@ScraperRegistry.register(category="custom")
class SambaNovaScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="sambanova", company_name="SambaNova", careers_url="https://sambanova.ai/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/sambanovasystems/jobs"

@ScraperRegistry.register(category="custom")
class SourcegraphScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="sourcegraph", company_name="Sourcegraph", careers_url="https://sourcegraph.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/sourcegraph/jobs"

@ScraperRegistry.register(category="custom")
class TempusScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="tempus", company_name="Tempus", careers_url="https://tempus.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/tempus/jobs"

@ScraperRegistry.register(category="custom")
class TemporalScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="temporal", company_name="Temporal", careers_url="https://temporal.io/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/temporaltechnologies/jobs"

@ScraperRegistry.register(category="custom")
class WriterScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="writer", company_name="Writer", careers_url="https://writer.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/writerai/jobs"

@ScraperRegistry.register(category="custom")
class LambdaScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="lambda", company_name="Lambda", careers_url="https://lambdalabs.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/lambdalabs/jobs"

@ScraperRegistry.register(category="custom")
class KLAScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="kla", company_name="KLA", careers_url="https://kla.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/klatencor/jobs"

@ScraperRegistry.register(category="custom")
class AuroraScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="aurora", company_name="Aurora", careers_url="https://aurora.tech/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/auroradriver/jobs"

@ScraperRegistry.register(category="custom")
class ZscalerScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="zscaler", company_name="Zscaler", careers_url="https://zscaler.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/zscaler/jobs"


# Ashby Scrapers
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

@ScraperRegistry.register(category="custom")
class CohereScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="cohere", company_name="Cohere", careers_url="https://jobs.ashbyhq.com/cohere", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/cohere"

@ScraperRegistry.register(category="custom")
class SnowflakeScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="snowflake", company_name="Snowflake", careers_url="https://careers.snowflake.com/us/en/search-results", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/snowflake"

@ScraperRegistry.register(category="custom")
class LinearScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="linear", company_name="Linear", careers_url="https://linear.app/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/linear"


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
