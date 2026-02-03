"""Remaining company scrapers - Greenhouse, Lever, Ashby APIs."""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


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
class AgilentScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="agilent", company_name="Agilent", careers_url="https://agilent.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/agilenttechnologies/jobs"

@ScraperRegistry.register(category="custom")
class AnyscaleScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="anyscale", company_name="Anyscale", careers_url="https://jobs.ashbyhq.com/anyscale", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/anyscale"

# Broadcom moved to Workday - disabled for now (needs WorkdayHybridMixin from enterprise scrapers)
# @ScraperRegistry.register(category="custom")
# class BroadcomScraper - URL: https://broadcom.wd1.myworkdayjobs.com/External_Career

@ScraperRegistry.register(category="custom")
class CharacterAIScraper(AshbyMixin, HTTPScraper):
    config = ScraperConfig(company_slug="characterai", company_name="Character AI", careers_url="https://jobs.ashbyhq.com/character", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/character"

@ScraperRegistry.register(category="custom")
class CircleCIScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="circleci", company_name="CircleCI", careers_url="https://circleci.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/circleci/jobs"

@ScraperRegistry.register(category="custom")
class CrowdstrikeScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="crowdstrike", company_name="Crowdstrike", careers_url="https://crowdstrike.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/crowdstrike/jobs"

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
