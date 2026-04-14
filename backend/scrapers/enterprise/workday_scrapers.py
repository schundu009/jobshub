"""
Workday-based enterprise scrapers using pure HTTP API (no Playwright/Chromium).

All 93 companies use Workday ATS which exposes a free JSON API at
/wday/cxs/{tenant}/{path}/jobs. The WorkdayMixin from remaining_scrapers
handles pagination, request construction, and job parsing.

This replaces the previous hybrid HTTP/Playwright approach that caused
Chromium OOM crashes on Railway.
"""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry
from scrapers.custom.remaining_scrapers import WorkdayMixin


# ---------------------------------------------------------------------------
# Retail
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class WalmartWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="walmart", company_name="Walmart", careers_url="https://walmart.wd5.myworkdayjobs.com/WalmartExternal", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://walmart.wd5.myworkdayjobs.com/wday/cxs/walmart/walmartexternal/jobs"


@ScraperRegistry.register(category="enterprise")
class TargetWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="target", company_name="Target", careers_url="https://target.wd5.myworkdayjobs.com/targetcareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://target.wd5.myworkdayjobs.com/wday/cxs/target/targetcareers/jobs"


@ScraperRegistry.register(category="enterprise")
class HomeDepotWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="homedepot", company_name="Home Depot", careers_url="https://homedepot.wd5.myworkdayjobs.com/CareerDepot", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://homedepot.wd5.myworkdayjobs.com/wday/cxs/homedepot/careerdepot/jobs"


@ScraperRegistry.register(category="enterprise")
class KohlsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="kohls", company_name="Kohl's", careers_url="https://kohls.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://kohls.wd5.myworkdayjobs.com/wday/cxs/kohls/external/jobs"


@ScraperRegistry.register(category="enterprise")
class NordstromWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="nordstrom", company_name="Nordstrom", careers_url="https://nordstrom.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://nordstrom.wd5.myworkdayjobs.com/wday/cxs/nordstrom/external/jobs"


@ScraperRegistry.register(category="enterprise")
class GapWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="gap", company_name="Gap Inc.", careers_url="https://gap.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://gap.wd5.myworkdayjobs.com/wday/cxs/gap/external/jobs"


@ScraperRegistry.register(category="enterprise")
class LululemonWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="lululemon", company_name="Lululemon", careers_url="https://lululemon.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://lululemon.wd1.myworkdayjobs.com/wday/cxs/lululemon/external/jobs"


@ScraperRegistry.register(category="enterprise")
class ChipotleWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="chipotle", company_name="Chipotle", careers_url="https://chipotle.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://chipotle.wd1.myworkdayjobs.com/wday/cxs/chipotle/external/jobs"


# ---------------------------------------------------------------------------
# Tech & Media
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class AdobeWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="adobe", company_name="Adobe", careers_url="https://adobe.wd5.myworkdayjobs.com/external_experienced", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://adobe.wd5.myworkdayjobs.com/wday/cxs/adobe/external_experienced/jobs"


@ScraperRegistry.register(category="enterprise")
class BroadcomWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="broadcom", company_name="Broadcom", careers_url="https://broadcom.wd1.myworkdayjobs.com/External_Career", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://broadcom.wd1.myworkdayjobs.com/wday/cxs/broadcom/external_career/jobs"


@ScraperRegistry.register(category="enterprise")
class NetflixWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="netflix", company_name="Netflix", careers_url="https://netflix.wd1.myworkdayjobs.com/Netflix", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://netflix.wd1.myworkdayjobs.com/wday/cxs/netflix/netflix/jobs"


@ScraperRegistry.register(category="enterprise")
class NvidiaWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="nvidia", company_name="Nvidia", careers_url="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/nvidiaexternalcareersite/jobs"


@ScraperRegistry.register(category="enterprise")
class HPWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="hp", company_name="HP Inc.", careers_url="https://hp.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://hp.wd5.myworkdayjobs.com/wday/cxs/hp/external/jobs"


@ScraperRegistry.register(category="enterprise")
class WesternDigitalWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="westerndigital", company_name="Western Digital", careers_url="https://westerndigital.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://westerndigital.wd5.myworkdayjobs.com/wday/cxs/westerndigital/external/jobs"


@ScraperRegistry.register(category="enterprise")
class MotorolaSolutionsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="motorolasolutions", company_name="Motorola Solutions", careers_url="https://motorolasolutions.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://motorolasolutions.wd5.myworkdayjobs.com/wday/cxs/motorolasolutions/external/jobs"


@ScraperRegistry.register(category="enterprise")
class EbayWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="ebay", company_name="eBay", careers_url="https://ebay.wd5.myworkdayjobs.com/apply", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://ebay.wd5.myworkdayjobs.com/wday/cxs/ebay/apply/jobs"


@ScraperRegistry.register(category="enterprise")
class EquinixWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="equinix", company_name="Equinix", careers_url="https://equinix.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://equinix.wd5.myworkdayjobs.com/wday/cxs/equinix/external/jobs"


# ---------------------------------------------------------------------------
# Consulting & Professional Services
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class AccentureWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="accenture", company_name="Accenture", careers_url="https://accenture.wd103.myworkdayjobs.com/AccentureCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/accenturecareers/jobs"


@ScraperRegistry.register(category="enterprise")
class PwCWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pwc", company_name="PwC", careers_url="https://pwc.wd3.myworkdayjobs.com/Global_Experienced_Careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://pwc.wd3.myworkdayjobs.com/wday/cxs/pwc/global_experienced_careers/jobs"


@ScraperRegistry.register(category="enterprise")
class DeloitteWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="deloitte", company_name="Deloitte", careers_url="https://deloitteie.wd3.myworkdayjobs.com/Experienced_Professionals", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://deloitteie.wd3.myworkdayjobs.com/wday/cxs/deloitteie/experienced_professionals/jobs"


@ScraperRegistry.register(category="enterprise")
class CognizantWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="cognizant", company_name="Cognizant", careers_url="https://cognizant.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://cognizant.wd1.myworkdayjobs.com/wday/cxs/cognizant/external/jobs"


@ScraperRegistry.register(category="enterprise")
class CapgeminiWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="capgemini", company_name="Capgemini", careers_url="https://capgemini.wd3.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://capgemini.wd3.myworkdayjobs.com/wday/cxs/capgemini/external/jobs"


@ScraperRegistry.register(category="enterprise")
class DXCWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="dxc", company_name="DXC Technology", careers_url="https://dxc.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://dxc.wd1.myworkdayjobs.com/wday/cxs/dxc/external/jobs"


@ScraperRegistry.register(category="enterprise")
class BoozAllenWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="boozallen", company_name="Booz Allen Hamilton", careers_url="https://boozallen.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://boozallen.wd1.myworkdayjobs.com/wday/cxs/boozallen/external/jobs"


@ScraperRegistry.register(category="enterprise")
class JLLWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="jll", company_name="Jones Lang LaSalle", careers_url="https://jll.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://jll.wd1.myworkdayjobs.com/wday/cxs/jll/external/jobs"


# ---------------------------------------------------------------------------
# Banking & Finance
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class WellsFargoWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="wellsfargo", company_name="Wells Fargo", careers_url="https://wf.wd1.myworkdayjobs.com/WellsFargoJobs", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://wf.wd1.myworkdayjobs.com/wday/cxs/wf/wellsfargojobs/jobs"


@ScraperRegistry.register(category="enterprise")
class BankOfAmericaWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="bankofamerica", company_name="Bank of America", careers_url="https://ghr.wd1.myworkdayjobs.com/Lateral-US", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://ghr.wd1.myworkdayjobs.com/wday/cxs/ghr/lateral-us/jobs"


@ScraperRegistry.register(category="enterprise")
class MorganStanleyWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="morganstanley", company_name="Morgan Stanley", careers_url="https://ms.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://ms.wd5.myworkdayjobs.com/wday/cxs/ms/external/jobs"


@ScraperRegistry.register(category="enterprise")
class CitiWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="citi", company_name="Citibank", careers_url="https://citi.wd5.myworkdayjobs.com/2", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://citi.wd5.myworkdayjobs.com/wday/cxs/citi/2/jobs"


@ScraperRegistry.register(category="enterprise")
class BlackRockWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="blackrock", company_name="BlackRock", careers_url="https://blackrock.wd1.myworkdayjobs.com/BlackRock_Professional", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://blackrock.wd1.myworkdayjobs.com/wday/cxs/blackrock/blackrock_professional/jobs"


@ScraperRegistry.register(category="enterprise")
class MastercardWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="mastercard", company_name="Mastercard", careers_url="https://mastercard.wd1.myworkdayjobs.com/Campus", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://mastercard.wd1.myworkdayjobs.com/wday/cxs/mastercard/campus/jobs"


@ScraperRegistry.register(category="enterprise")
class PNCWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pnc", company_name="PNC Bank", careers_url="https://pnc.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://pnc.wd5.myworkdayjobs.com/wday/cxs/pnc/external/jobs"


@ScraperRegistry.register(category="enterprise")
class SchwabWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="schwab", company_name="Charles Schwab", careers_url="https://schwab.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://schwab.wd1.myworkdayjobs.com/wday/cxs/schwab/external/jobs"


@ScraperRegistry.register(category="enterprise")
class DiscoverWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="discover", company_name="Discover Financial", careers_url="https://discover.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://discover.wd5.myworkdayjobs.com/wday/cxs/discover/external/jobs"


@ScraperRegistry.register(category="enterprise")
class FifthThirdWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="fifththird", company_name="Fifth Third Bank", careers_url="https://fifththird.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://fifththird.wd5.myworkdayjobs.com/wday/cxs/fifththird/external/jobs"


@ScraperRegistry.register(category="enterprise")
class KeyBankWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="keybank", company_name="KeyBank", careers_url="https://keybank.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://keybank.wd5.myworkdayjobs.com/wday/cxs/keybank/external/jobs"


@ScraperRegistry.register(category="enterprise")
class MTBankWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="mtbank", company_name="M&T Bank", careers_url="https://mtbank.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://mtbank.wd5.myworkdayjobs.com/wday/cxs/mtbank/external/jobs"


@ScraperRegistry.register(category="enterprise")
class RegionsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="regions", company_name="Regions Bank", careers_url="https://regions.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://regions.wd5.myworkdayjobs.com/wday/cxs/regions/external/jobs"


@ScraperRegistry.register(category="enterprise")
class HuntingtonWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="huntington", company_name="Huntington Bank", careers_url="https://huntington.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://huntington.wd5.myworkdayjobs.com/wday/cxs/huntington/external/jobs"


@ScraperRegistry.register(category="enterprise")
class FiservWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="fiserv", company_name="Fiserv", careers_url="https://fiserv.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://fiserv.wd5.myworkdayjobs.com/wday/cxs/fiserv/external/jobs"


@ScraperRegistry.register(category="enterprise")
class FranklinTempletonWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="franklintempleton", company_name="Franklin Templeton", careers_url="https://franklintempleton.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://franklintempleton.wd5.myworkdayjobs.com/wday/cxs/franklintempleton/external/jobs"


@ScraperRegistry.register(category="enterprise")
class FreddieMacWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="freddiemac", company_name="Freddie Mac", careers_url="https://freddiemac.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://freddiemac.wd1.myworkdayjobs.com/wday/cxs/freddiemac/external/jobs"


@ScraperRegistry.register(category="enterprise")
class FannieMaeWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="fanniemae", company_name="Fannie Mae", careers_url="https://fanniemae.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://fanniemae.wd5.myworkdayjobs.com/wday/cxs/fanniemae/external/jobs"


@ScraperRegistry.register(category="enterprise")
class MarshMcLennanWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="mmc", company_name="Marsh McLennan", careers_url="https://mmc.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://mmc.wd1.myworkdayjobs.com/wday/cxs/mmc/external/jobs"


# ---------------------------------------------------------------------------
# Insurance
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class TravelersWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="travelers", company_name="Travelers", careers_url="https://travelers.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://travelers.wd5.myworkdayjobs.com/wday/cxs/travelers/external/jobs"


@ScraperRegistry.register(category="enterprise")
class HartfordWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="hartford", company_name="Hartford Insurance", careers_url="https://hartford.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://hartford.wd5.myworkdayjobs.com/wday/cxs/hartford/external/jobs"


@ScraperRegistry.register(category="enterprise")
class HumanaWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="humana", company_name="Humana", careers_url="https://humana.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://humana.wd5.myworkdayjobs.com/wday/cxs/humana/external/jobs"


@ScraperRegistry.register(category="enterprise")
class PrudentialWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="prudential", company_name="Prudential", careers_url="https://prudential.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://prudential.wd5.myworkdayjobs.com/wday/cxs/prudential/external/jobs"


@ScraperRegistry.register(category="enterprise")
class MassMutualWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="massmutual", company_name="MassMutual", careers_url="https://massmutual.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://massmutual.wd5.myworkdayjobs.com/wday/cxs/massmutual/external/jobs"


# ---------------------------------------------------------------------------
# Pharma & Healthcare
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class PfizerWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pfizer", company_name="Pfizer", careers_url="https://pfizer.wd1.myworkdayjobs.com/PfizerCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://pfizer.wd1.myworkdayjobs.com/wday/cxs/pfizer/pfizercareers/jobs"


@ScraperRegistry.register(category="enterprise")
class MerckWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="merck", company_name="Merck", careers_url="https://merck.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://merck.wd5.myworkdayjobs.com/wday/cxs/merck/external/jobs"


@ScraperRegistry.register(category="enterprise")
class BMSWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="bms", company_name="Bristol-Myers Squibb", careers_url="https://bms.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://bms.wd5.myworkdayjobs.com/wday/cxs/bms/external/jobs"


@ScraperRegistry.register(category="enterprise")
class AmgenWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="amgen", company_name="Amgen", careers_url="https://amgen.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://amgen.wd5.myworkdayjobs.com/wday/cxs/amgen/external/jobs"


@ScraperRegistry.register(category="enterprise")
class BiogenWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="biogen", company_name="Biogen", careers_url="https://biogen.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://biogen.wd5.myworkdayjobs.com/wday/cxs/biogen/external/jobs"


@ScraperRegistry.register(category="enterprise")
class ThermoFisherWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="thermofisher", company_name="Thermo Fisher", careers_url="https://thermofisher.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://thermofisher.wd5.myworkdayjobs.com/wday/cxs/thermofisher/external/jobs"


@ScraperRegistry.register(category="enterprise")
class CardinalHealthWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="cardinalhealth", company_name="Cardinal Health", careers_url="https://cardinalhealth.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://cardinalhealth.wd1.myworkdayjobs.com/wday/cxs/cardinalhealth/external/jobs"


@ScraperRegistry.register(category="enterprise")
class DaVitaWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="davita", company_name="DaVita", careers_url="https://davita.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://davita.wd1.myworkdayjobs.com/wday/cxs/davita/external/jobs"


@ScraperRegistry.register(category="enterprise")
class OptumWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="optum", company_name="Optum", careers_url="https://optum.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://optum.wd5.myworkdayjobs.com/wday/cxs/optum/external/jobs"


@ScraperRegistry.register(category="enterprise")
class WalgreensWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="walgreens", company_name="Walgreens", careers_url="https://walgreens.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://walgreens.wd5.myworkdayjobs.com/wday/cxs/walgreens/external/jobs"


# ---------------------------------------------------------------------------
# Defense & Aerospace
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class NorthropGrummanWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="northropgrumman", company_name="Northrop Grumman", careers_url="https://ngc.wd1.myworkdayjobs.com/Northrop_Grumman_External_Site", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://ngc.wd1.myworkdayjobs.com/wday/cxs/ngc/northrop_grumman_external_site/jobs"


@ScraperRegistry.register(category="enterprise")
class RTXWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="rtx", company_name="RTX Corporation", careers_url="https://globalhr.wd5.myworkdayjobs.com/REC_RTX_Ext_Gateway", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://globalhr.wd5.myworkdayjobs.com/wday/cxs/globalhr/rec_rtx_ext_gateway/jobs"


@ScraperRegistry.register(category="enterprise")
class LeidosWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="leidos", company_name="Leidos", careers_url="https://leidos.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://leidos.wd5.myworkdayjobs.com/wday/cxs/leidos/external/jobs"


@ScraperRegistry.register(category="enterprise")
class BAEWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="bae", company_name="BAE Systems", careers_url="https://bae.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://bae.wd1.myworkdayjobs.com/wday/cxs/bae/external/jobs"


# ---------------------------------------------------------------------------
# Energy & Industrial
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class ChevronWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="chevron", company_name="Chevron", careers_url="https://chevron.wd5.myworkdayjobs.com/jobs", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://chevron.wd5.myworkdayjobs.com/wday/cxs/chevron/jobs/jobs"


@ScraperRegistry.register(category="enterprise")
class ExxonMobilWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="exxonmobil", company_name="ExxonMobil", careers_url="https://exxonmobil.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://exxonmobil.wd5.myworkdayjobs.com/wday/cxs/exxonmobil/external/jobs"


@ScraperRegistry.register(category="enterprise")
class CaterpillarWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="caterpillar", company_name="Caterpillar", careers_url="https://caterpillar.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://caterpillar.wd5.myworkdayjobs.com/wday/cxs/caterpillar/external/jobs"


@ScraperRegistry.register(category="enterprise")
class GEWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="ge", company_name="General Electric", careers_url="https://ge.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://ge.wd5.myworkdayjobs.com/wday/cxs/ge/external/jobs"


@ScraperRegistry.register(category="enterprise")
class DuPontWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="dupont", company_name="DuPont", careers_url="https://dupont.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://dupont.wd5.myworkdayjobs.com/wday/cxs/dupont/external/jobs"


@ScraperRegistry.register(category="enterprise")
class DowWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="dow", company_name="Dow Chemical", careers_url="https://dow.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://dow.wd5.myworkdayjobs.com/wday/cxs/dow/external/jobs"


@ScraperRegistry.register(category="enterprise")
class AppliedMaterialsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="appliedmaterials", company_name="Applied Materials", careers_url="https://appliedmaterials.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://appliedmaterials.wd5.myworkdayjobs.com/wday/cxs/appliedmaterials/external/jobs"


@ScraperRegistry.register(category="enterprise")
class ConocoPhillipsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="conocophillips", company_name="ConocoPhillips", careers_url="https://conocophillips.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://conocophillips.wd5.myworkdayjobs.com/wday/cxs/conocophillips/external/jobs"


@ScraperRegistry.register(category="enterprise")
class MarathonWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="marathon", company_name="Marathon Petroleum", careers_url="https://marathon.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://marathon.wd5.myworkdayjobs.com/wday/cxs/marathon/external/jobs"


@ScraperRegistry.register(category="enterprise")
class ThreeMWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="3m", company_name="3M Company", careers_url="https://3m.wd1.myworkdayjobs.com/Search", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://3m.wd1.myworkdayjobs.com/wday/cxs/3m/search/jobs"


# ---------------------------------------------------------------------------
# Consumer & Food
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class PGWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pg", company_name="Procter & Gamble", careers_url="https://pg.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://pg.wd5.myworkdayjobs.com/wday/cxs/pg/external/jobs"


@ScraperRegistry.register(category="enterprise")
class KimberlyClarkWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="kimberlyclark", company_name="Kimberly-Clark", careers_url="https://kimberlyclark.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://kimberlyclark.wd5.myworkdayjobs.com/wday/cxs/kimberlyclark/external/jobs"


@ScraperRegistry.register(category="enterprise")
class TysonWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="tyson", company_name="Tyson Foods", careers_url="https://tyson.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://tyson.wd5.myworkdayjobs.com/wday/cxs/tyson/external/jobs"


@ScraperRegistry.register(category="enterprise")
class MondelezWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="mondelez", company_name="Mondelez", careers_url="https://mondelez.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://mondelez.wd1.myworkdayjobs.com/wday/cxs/mondelez/external/jobs"


@ScraperRegistry.register(category="enterprise")
class SmuckerWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="smucker", company_name="J.M. Smucker", careers_url="https://smucker.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://smucker.wd1.myworkdayjobs.com/wday/cxs/smucker/external/jobs"


@ScraperRegistry.register(category="enterprise")
class USFoodsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="usfoods", company_name="US Foods", careers_url="https://usfoods.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://usfoods.wd5.myworkdayjobs.com/wday/cxs/usfoods/external/jobs"


# ---------------------------------------------------------------------------
# Transportation & Logistics
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class FedExWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="fedex", company_name="FedEx", careers_url="https://fedex.wd1.myworkdayjobs.com/FXE_External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://fedex.wd1.myworkdayjobs.com/wday/cxs/fedex/fxe_external/jobs"


@ScraperRegistry.register(category="enterprise")
class SouthwestWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="southwest", company_name="Southwest Airlines", careers_url="https://southwest.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://southwest.wd5.myworkdayjobs.com/wday/cxs/southwest/external/jobs"


@ScraperRegistry.register(category="enterprise")
class JBHuntWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="jbhunt", company_name="J.B. Hunt", careers_url="https://jbhunt.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://jbhunt.wd5.myworkdayjobs.com/wday/cxs/jbhunt/external/jobs"


# ---------------------------------------------------------------------------
# Telecom
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class ATTWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="att", company_name="AT&T", careers_url="https://att.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://att.wd5.myworkdayjobs.com/wday/cxs/att/external/jobs"


# ---------------------------------------------------------------------------
# Real Estate & Construction
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class LennarWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="lennar", company_name="Lennar Homes", careers_url="https://lennar.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://lennar.wd1.myworkdayjobs.com/wday/cxs/lennar/external/jobs"


@ScraperRegistry.register(category="enterprise")
class TollBrothersWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="tollbrothers", company_name="Toll Brothers", careers_url="https://tollbrothers.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://tollbrothers.wd1.myworkdayjobs.com/wday/cxs/tollbrothers/external/jobs"


# ---------------------------------------------------------------------------
# European / Global
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class VodafoneWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="vodafone", company_name="Vodafone", careers_url="https://vodafone.wd3.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://vodafone.wd3.myworkdayjobs.com/wday/cxs/vodafone/external/jobs"


@ScraperRegistry.register(category="enterprise")
class UnileverWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="unilever", company_name="Unilever", careers_url="https://unilever.wd3.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://unilever.wd3.myworkdayjobs.com/wday/cxs/unilever/external/jobs"


@ScraperRegistry.register(category="enterprise")
class SiemensWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="siemens", company_name="Siemens", careers_url="https://siemens.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://siemens.wd1.myworkdayjobs.com/wday/cxs/siemens/external/jobs"


@ScraperRegistry.register(category="enterprise")
class BoschWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="bosch", company_name="Bosch", careers_url="https://bosch.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://bosch.wd1.myworkdayjobs.com/wday/cxs/bosch/external/jobs"


@ScraperRegistry.register(category="enterprise")
class PhilipsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="philips", company_name="Philips", careers_url="https://philips.wd3.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://philips.wd3.myworkdayjobs.com/wday/cxs/philips/external/jobs"


@ScraperRegistry.register(category="enterprise")
class ShellWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="shell", company_name="Shell", careers_url="https://shell.wd3.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://shell.wd3.myworkdayjobs.com/wday/cxs/shell/external/jobs"


@ScraperRegistry.register(category="enterprise")
class BPWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="bp", company_name="BP", careers_url="https://bp.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://bp.wd1.myworkdayjobs.com/wday/cxs/bp/external/jobs"


@ScraperRegistry.register(category="enterprise")
class DHLWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="dhl", company_name="DHL", careers_url="https://dhl.wd3.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://dhl.wd3.myworkdayjobs.com/wday/cxs/dhl/external/jobs"
