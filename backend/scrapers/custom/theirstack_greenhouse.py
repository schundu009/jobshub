"""IT company scrapers discovered via TheirStack API - Greenhouse."""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry
from scrapers.custom.remaining_scrapers import GreenhouseMixin, WorkdayMixin


# GreenhouseMixin is shared with remaining_scrapers.py; it honors the
# auto-heal url_override via BaseScraper.resolve_api_url().


# VarsityTutorsANerdyCompanyScraper — Greenhouse board 404 (migrated off Greenhouse)
# TalentifyIoScraper — Greenhouse board 404 (migrated off Greenhouse)

# PandologicScraper — Greenhouse board 404 (migrated off Greenhouse)
# ShopeeScraper — Greenhouse board 404 (migrated off Greenhouse)

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

# OutlierAiScraper — Greenhouse board 404 (migrated off Greenhouse)

@ScraperRegistry.register(category="custom")
class DoordashScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="doordash", company_name="DoorDash", careers_url="https://doordash.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/doordashusa/jobs"

# WarbyParkerScraper — Greenhouse board 404 (migrated off Greenhouse)

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
class CelonisScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="celonis", company_name="Celonis", careers_url="https://celonis.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/celonis/jobs"

# Moved to Workday (unitytech.wd1 / Unity) (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class UnityTechnologiesScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="unity3d", company_name="Unity Technologies", careers_url="https://unitytech.wd1.myworkdayjobs.com/Unity", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://unitytech.wd1.myworkdayjobs.com/wday/cxs/unitytech/Unity/jobs"

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
class ElasticScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="elastic", company_name="Elastic", careers_url="https://elastic.co/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/elastic/jobs"

@ScraperRegistry.register(category="custom")
class RiotGamesScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="riotgames", company_name="Riot Games", careers_url="https://riotgames.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/riotgames/jobs"

@ScraperRegistry.register(category="custom")
class PinterestScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pinterest", company_name="Pinterest", careers_url="https://pinterest.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/pinterest/jobs"

# VivianHealthScraper — Greenhouse board 404 (moved to Ashby: ashbyhq.com/vivian-health)

@ScraperRegistry.register(category="custom")
class LushCosmeticsScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="lush", company_name="Lush Cosmetics", careers_url="https://lush.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/lush/jobs"

# LightspeedScraper — Greenhouse board 404 (moved to Ashby: api.ashbyhq.com/posting-api/job-board/lightspeed)

# board dead as of 2026-09-29; Greenhouse board empty, SmartRecruiters 'ripplematch' has only a test posting
@ScraperRegistry.register(category="custom")
class RipplematchScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="ripplematch", company_name="RippleMatch", careers_url="https://ripplematch.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10, enabled=False, disabled_reason="board dead as of 2026-09-29; Greenhouse board empty, SmartRecruiters 'ripplematch' has only a test posting")
    API_URL = "https://boards-api.greenhouse.io/v1/boards/ripplematch/jobs"

@ScraperRegistry.register(category="custom")
class NewRelicScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="newrelic", company_name="New Relic", careers_url="https://newrelic.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/newrelic/jobs"

@ScraperRegistry.register(category="custom")
class EpicGamesScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="epicgames", company_name="Epic Games", careers_url="https://epicgames.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/epicgames/jobs"

@ScraperRegistry.register(category="custom")
class DoctolibScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="doctolib", company_name="Doctolib", careers_url="https://doctolib.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/doctolib/jobs"

@ScraperRegistry.register(category="custom")
class OkxScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="okx", company_name="OKX", careers_url="https://okx.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/okx/jobs"

# Greenhouse board renamed hubspot -> hubspotjobs (verified 2026-09-29)
@ScraperRegistry.register(category="custom")
class HubspotScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="hubspot", company_name="HubSpot", careers_url="https://hubspot.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/hubspotjobs/jobs"

@ScraperRegistry.register(category="custom")
class VerkadaScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="verkada", company_name="Verkada", careers_url="https://verkada.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/verkada/jobs"

@ScraperRegistry.register(category="custom")
class SpaceXScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="spacex", company_name="SpaceX", careers_url="https://spacex.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/spacex/jobs"

# ── Infrastructure / DevOps-heavy companies (added 2026-04-15) ──────────

@ScraperRegistry.register(category="custom")
class DatadogScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="datadog", company_name="Datadog", careers_url="https://datadog.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/datadog/jobs"

@ScraperRegistry.register(category="custom")
class PagerDutyScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pagerduty", company_name="PagerDuty", careers_url="https://pagerduty.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/pagerduty/jobs"

@ScraperRegistry.register(category="custom")
class CloudflareScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="cloudflare", company_name="Cloudflare", careers_url="https://cloudflare.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/cloudflare/jobs"

@ScraperRegistry.register(category="custom")
class ElasticScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="elastic", company_name="Elastic", careers_url="https://elastic.co/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/elastic/jobs"

@ScraperRegistry.register(category="custom")
class NewRelicScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="newrelic", company_name="New Relic", careers_url="https://newrelic.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/newrelic/jobs"

@ScraperRegistry.register(category="custom")
class FastlyScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="fastly", company_name="Fastly", careers_url="https://fastly.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/fastly/jobs"

@ScraperRegistry.register(category="custom")
class MongoDBScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="mongodb", company_name="MongoDB", careers_url="https://mongodb.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/mongodb/jobs"

@ScraperRegistry.register(category="custom")
class CockroachLabsScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="cockroachlabs", company_name="Cockroach Labs", careers_url="https://cockroachlabs.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/cockroachlabs/jobs"

@ScraperRegistry.register(category="custom")
class TwilioScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="twilio", company_name="Twilio", careers_url="https://twilio.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/twilio/jobs"

# ── Major tech companies with high volume ────────────────────────────────

@ScraperRegistry.register(category="custom")
class AirbnbScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="airbnb", company_name="Airbnb", careers_url="https://airbnb.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/airbnb/jobs"

@ScraperRegistry.register(category="custom")
class LyftScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="lyft", company_name="Lyft", careers_url="https://lyft.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/lyft/jobs"

@ScraperRegistry.register(category="custom")
class InstacartScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="instacart", company_name="Instacart", careers_url="https://instacart.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/instacart/jobs"

@ScraperRegistry.register(category="custom")
class PinterestScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pinterest", company_name="Pinterest", careers_url="https://pinterest.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/pinterest/jobs"

@ScraperRegistry.register(category="custom")
class RedditScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="reddit", company_name="Reddit", careers_url="https://reddit.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/reddit/jobs"

@ScraperRegistry.register(category="custom")
class BlockScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="block", company_name="Block (Square)", careers_url="https://block.xyz/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/block/jobs"

@ScraperRegistry.register(category="custom")
class BrexScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="brex", company_name="Brex", careers_url="https://brex.com/careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/brex/jobs"

@ScraperRegistry.register(category="custom")
class GitLabScraper(GreenhouseMixin, HTTPScraper):
    config = ScraperConfig(company_slug="gitlab", company_name="GitLab", careers_url="https://gitlab.com/jobs", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=10)
    API_URL = "https://boards-api.greenhouse.io/v1/boards/gitlab/jobs"
