"""IT company scrapers discovered via TheirStack API - Greenhouse."""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


class GreenhouseMixin:
    """Mixin for Greenhouse job board scraping."""
    
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



@ScraperRegistry.register(category="custom")
class VarsityTutorsANerdyCompanyScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="varsitytutors", company_name="Varsity Tutors, a Nerdy Company", careers_url="https://varsitytutors.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/varsitytutors/jobs"

@ScraperRegistry.register(category="custom")
class TalentifyIoScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="talentify", company_name="Talentify.io", careers_url="https://talentify.io/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/talentify/jobs"

@ScraperRegistry.register(category="custom")
class PandologicScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pandologic", company_name="PandoLogic", careers_url="https://pandologic.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/pandologic/jobs"

@ScraperRegistry.register(category="custom")
class ShopeeScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="shopee", company_name="Shopee", careers_url="https://shopee.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/shopee/jobs"

@ScraperRegistry.register(category="custom")
class CarvanaScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="carvana", company_name="Carvana", careers_url="https://carvana.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/carvana/jobs"

@ScraperRegistry.register(category="custom")
class CanonicalScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="canonical", company_name="Canonical", careers_url="https://canonical.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/canonical/jobs"

@ScraperRegistry.register(category="custom")
class AgodaScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="agoda", company_name="Agoda", careers_url="https://agoda.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/agoda/jobs"

@ScraperRegistry.register(category="custom")
class OktaScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="okta", company_name="Okta", careers_url="https://okta.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/okta/jobs"

@ScraperRegistry.register(category="custom")
class OutlierAiScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="outlier", company_name="Outlier AI", careers_url="https://outlier.ai/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/outlier/jobs"

@ScraperRegistry.register(category="custom")
class DoordashScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="doordash", company_name="DoorDash", careers_url="https://doordash.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/doordash/jobs"

@ScraperRegistry.register(category="custom")
class WarbyParkerScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="warbyparker", company_name="Warby Parker", careers_url="https://warbyparker.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/warbyparker/jobs"

@ScraperRegistry.register(category="custom")
class TwilioScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="twilio", company_name="Twilio", careers_url="https://twilio.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/twilio/jobs"

@ScraperRegistry.register(category="custom")
class MongodbScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="mongodb", company_name="MongoDB", careers_url="https://mongodb.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/mongodb/jobs"

@ScraperRegistry.register(category="custom")
class CloudflareScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="cloudflare", company_name="Cloudflare", careers_url="https://cloudflare.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs"

@ScraperRegistry.register(category="custom")
class DeliverooScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="deliveroouk", company_name="Deliveroo", careers_url="https://deliveroo.co.uk/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/deliveroo/jobs"

@ScraperRegistry.register(category="custom")
class CelonisScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="celonis", company_name="Celonis", careers_url="https://celonis.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/celonis/jobs"

@ScraperRegistry.register(category="custom")
class UnityTechnologiesScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="unity3d", company_name="Unity Technologies", careers_url="https://unity3d.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/unity3d/jobs"

@ScraperRegistry.register(category="custom")
class SobeysScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="sobeys", company_name="Sobeys", careers_url="https://sobeys.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/sobeys/jobs"

@ScraperRegistry.register(category="custom")
class PureStorageScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="purestorage", company_name="Pure Storage", careers_url="https://purestorage.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/purestorage/jobs"

@ScraperRegistry.register(category="custom")
class SamsaraScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="samsara", company_name="Samsara", careers_url="https://samsara.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/samsara/jobs"

@ScraperRegistry.register(category="custom")
class CoupangScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="coupangjobs", company_name="Coupang", careers_url="https://coupang.jobs/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/coupang/jobs"

@ScraperRegistry.register(category="custom")
class DatadogScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="datadoghq", company_name="Datadog", careers_url="https://datadoghq.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/datadog/jobs"

@ScraperRegistry.register(category="custom")
class EsriScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="esri", company_name="Esri", careers_url="https://esri.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/esri/jobs"

@ScraperRegistry.register(category="custom")
class ChewyScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="chewy", company_name="Chewy", careers_url="https://chewy.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/chewy/jobs"

@ScraperRegistry.register(category="custom")
class ElasticScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="elastic", company_name="Elastic", careers_url="https://elastic.co/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/elastic/jobs"

@ScraperRegistry.register(category="custom")
class RiotGamesScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="riotgames", company_name="Riot Games", careers_url="https://riotgames.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/riotgames/jobs"

@ScraperRegistry.register(category="custom")
class SharkninjaScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="sharkninja", company_name="SharkNinja", careers_url="https://sharkninja.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/sharkninja/jobs"

@ScraperRegistry.register(category="custom")
class PinterestScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pinterest", company_name="Pinterest", careers_url="https://pinterest.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/pinterest/jobs"

@ScraperRegistry.register(category="custom")
class OcadoGroupScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="ocadogroup", company_name="Ocado Group", careers_url="https://ocadogroup.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/ocado/jobs"

@ScraperRegistry.register(category="custom")
class PelotonScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="onepeloton", company_name="Peloton", careers_url="https://onepeloton.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/onepeloton/jobs"

@ScraperRegistry.register(category="custom")
class VivianHealthScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="vivian", company_name="Vivian Health", careers_url="https://vivian.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/vivian/jobs"

@ScraperRegistry.register(category="custom")
class LushCosmeticsScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="lush", company_name="Lush Cosmetics", careers_url="https://lush.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/lush/jobs"

@ScraperRegistry.register(category="custom")
class LightspeedScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="lightspeedhq", company_name="Lightspeed", careers_url="https://lightspeedhq.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/lightspeedhq/jobs"

@ScraperRegistry.register(category="custom")
class RipplematchScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="ripplematch", company_name="RippleMatch", careers_url="https://ripplematch.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/ripplematch/jobs"

@ScraperRegistry.register(category="custom")
class ThgScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="thg", company_name="THG", careers_url="https://thg.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/thg/jobs"

@ScraperRegistry.register(category="custom")
class GreenThumbIndustriesScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="gtigrows", company_name="Green Thumb Industries", careers_url="https://gtigrows.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/gtigrows/jobs"

@ScraperRegistry.register(category="custom")
class NewRelicScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="newrelic", company_name="New Relic", careers_url="https://newrelic.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/newrelic/jobs"

@ScraperRegistry.register(category="custom")
class BoxScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="box", company_name="Box", careers_url="https://box.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/box/jobs"

@ScraperRegistry.register(category="custom")
class EpicGamesScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="epicgames", company_name="Epic Games", careers_url="https://epicgames.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/epicgames/jobs"

@ScraperRegistry.register(category="custom")
class FollettCorporationScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="follett", company_name="Follett Corporation", careers_url="https://follett.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/follett/jobs"

@ScraperRegistry.register(category="custom")
class DoctolibScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="doctolib", company_name="Doctolib", careers_url="https://doctolib.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/doctolib/jobs"

@ScraperRegistry.register(category="custom")
class OkxScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="okx", company_name="OKX", careers_url="https://okx.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/okx/jobs"

@ScraperRegistry.register(category="custom")
class GitlabScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="aboutgitlab", company_name="GitLab", careers_url="https://about.gitlab.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/aboutgitlab/jobs"

@ScraperRegistry.register(category="custom")
class CrocsScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="crocs", company_name="Crocs", careers_url="https://crocs.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/crocs/jobs"

@ScraperRegistry.register(category="custom")
class ZalandoScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="zalando", company_name="Zalando", careers_url="https://zalando.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/zalando/jobs"

@ScraperRegistry.register(category="custom")
class HubspotScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="hubspot", company_name="HubSpot", careers_url="https://hubspot.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/hubspot/jobs"

@ScraperRegistry.register(category="custom")
class VerkadaScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="verkada", company_name="Verkada", careers_url="https://verkada.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/verkada/jobs"

@ScraperRegistry.register(category="custom")
class SpaceXScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="spacex", company_name="SpaceX", careers_url="https://spacex.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/spacex/jobs"
