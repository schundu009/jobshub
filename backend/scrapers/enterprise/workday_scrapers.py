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
from scrapers.custom.remaining_scrapers import SmartRecruitersMixin, WorkdayMixin


# ---------------------------------------------------------------------------
# Retail
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class TargetWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="target", company_name="Target", careers_url="https://target.wd5.myworkdayjobs.com/targetcareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://target.wd5.myworkdayjobs.com/wday/cxs/target/targetcareers/jobs"


@ScraperRegistry.register(category="enterprise")
class HomeDepotWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="homedepot", company_name="Home Depot", careers_url="https://homedepot.wd5.myworkdayjobs.com/CareerDepot", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://homedepot.wd5.myworkdayjobs.com/wday/cxs/homedepot/careerdepot/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class KohlsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="kohls", company_name="Kohl's", careers_url="https://kohls.wd504.myworkdayjobs.com/kohlscareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://kohls.wd504.myworkdayjobs.com/wday/cxs/kohls/kohlscareers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class NordstromWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="nordstrom", company_name="Nordstrom", careers_url="https://nordstrom.wd501.myworkdayjobs.com/nordstrom_careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://nordstrom.wd501.myworkdayjobs.com/wday/cxs/nordstrom/nordstrom_careers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class GapWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="gap", company_name="Gap Inc.", careers_url="https://gapinc.wd1.myworkdayjobs.com/GAPINC", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://gapinc.wd1.myworkdayjobs.com/wday/cxs/gapinc/GAPINC/jobs"


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
class NvidiaWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="nvidia", company_name="Nvidia", careers_url="https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/nvidiaexternalcareersite/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class HPWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="hp", company_name="HP Inc.", careers_url="https://hp.wd5.myworkdayjobs.com/ExternalCareerSite", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://hp.wd5.myworkdayjobs.com/wday/cxs/hp/ExternalCareerSite/jobs"


# Not Workday: moved to SmartRecruiters 'WesternDigital' (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class WesternDigitalWorkdayScraper(SmartRecruitersMixin, HTTPScraper):
    config = ScraperConfig(company_slug="westerndigital", company_name="Western Digital", careers_url="https://jobs.smartrecruiters.com/WesternDigital", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://api.smartrecruiters.com/v1/companies/WesternDigital/postings"
    COMPANY_ID = "WesternDigital"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class MotorolaSolutionsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="motorolasolutions", company_name="Motorola Solutions", careers_url="https://motorolasolutions.wd5.myworkdayjobs.com/Careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://motorolasolutions.wd5.myworkdayjobs.com/wday/cxs/motorolasolutions/Careers/jobs"


@ScraperRegistry.register(category="enterprise")
class EbayWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="ebay", company_name="eBay", careers_url="https://ebay.wd5.myworkdayjobs.com/apply", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://ebay.wd5.myworkdayjobs.com/wday/cxs/ebay/apply/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class EquinixWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="equinix", company_name="Equinix", careers_url="https://equinix.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://equinix.wd1.myworkdayjobs.com/wday/cxs/equinix/External/jobs"


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


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class DXCWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="dxc", company_name="DXC Technology", careers_url="https://dxctechnology.wd1.myworkdayjobs.com/DXCJobs", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://dxctechnology.wd1.myworkdayjobs.com/wday/cxs/dxctechnology/DXCJobs/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class BoozAllenWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="boozallen", company_name="Booz Allen Hamilton", careers_url="https://bah.wd1.myworkdayjobs.com/BAH_Jobs", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://bah.wd1.myworkdayjobs.com/wday/cxs/bah/BAH_Jobs/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class JLLWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="jll", company_name="Jones Lang LaSalle", careers_url="https://jll.wd1.myworkdayjobs.com/jllcareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://jll.wd1.myworkdayjobs.com/wday/cxs/jll/jllcareers/jobs"


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


# Discover Financial: removed 2026-09-29 - merged into Capital One (see capitalone scraper).


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class FifthThirdWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="fifththird", company_name="Fifth Third Bank", careers_url="https://fifththird.wd5.myworkdayjobs.com/53careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://fifththird.wd5.myworkdayjobs.com/wday/cxs/fifththird/53careers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class MTBankWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="mtbank", company_name="M&T Bank", careers_url="https://mtb.wd5.myworkdayjobs.com/MTB", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://mtb.wd5.myworkdayjobs.com/wday/cxs/mtb/MTB/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class RegionsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="regions", company_name="Regions Bank", careers_url="https://regions.wd5.myworkdayjobs.com/Regions_Careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://regions.wd5.myworkdayjobs.com/wday/cxs/regions/Regions_Careers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class HuntingtonWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="huntington", company_name="Huntington Bank", careers_url="https://huntington.wd12.myworkdayjobs.com/HNBcareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://huntington.wd12.myworkdayjobs.com/wday/cxs/huntington/HNBcareers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class FiservWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="fiserv", company_name="Fiserv", careers_url="https://fiserv.wd5.myworkdayjobs.com/EXT", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://fiserv.wd5.myworkdayjobs.com/wday/cxs/fiserv/EXT/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class FreddieMacWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="freddiemac", company_name="Freddie Mac", careers_url="https://freddiemac.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://freddiemac.wd5.myworkdayjobs.com/wday/cxs/freddiemac/External/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class FannieMaeWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="fanniemae", company_name="Fannie Mae", careers_url="https://fanniemae.wd1.myworkdayjobs.com/FannieMaeCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://fanniemae.wd1.myworkdayjobs.com/wday/cxs/fanniemae/FannieMaeCareers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class MarshMcLennanWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="mmc", company_name="Marsh McLennan", careers_url="https://mmc.wd1.myworkdayjobs.com/MMC", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://mmc.wd1.myworkdayjobs.com/wday/cxs/mmc/MMC/jobs"


# ---------------------------------------------------------------------------
# Insurance
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class TravelersWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="travelers", company_name="Travelers", careers_url="https://travelers.wd5.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://travelers.wd5.myworkdayjobs.com/wday/cxs/travelers/external/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class HartfordWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="hartford", company_name="Hartford Insurance", careers_url="https://thehartford.wd5.myworkdayjobs.com/Careers_External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://thehartford.wd5.myworkdayjobs.com/wday/cxs/thehartford/Careers_External/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class HumanaWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="humana", company_name="Humana", careers_url="https://humana.wd5.myworkdayjobs.com/Humana_External_Career_Site", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://humana.wd5.myworkdayjobs.com/wday/cxs/humana/Humana_External_Career_Site/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class PrudentialWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="prudential", company_name="Prudential", careers_url="https://pru.wd5.myworkdayjobs.com/Careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://pru.wd5.myworkdayjobs.com/wday/cxs/pru/Careers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class MassMutualWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="massmutual", company_name="MassMutual", careers_url="https://massmutual.wd1.myworkdayjobs.com/MMCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://massmutual.wd1.myworkdayjobs.com/wday/cxs/massmutual/MMCareers/jobs"


# ---------------------------------------------------------------------------
# Pharma & Healthcare
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class PfizerWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pfizer", company_name="Pfizer", careers_url="https://pfizer.wd1.myworkdayjobs.com/PfizerCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://pfizer.wd1.myworkdayjobs.com/wday/cxs/pfizer/pfizercareers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class MerckWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="merck", company_name="Merck", careers_url="https://msd.wd5.myworkdayjobs.com/SearchJobs", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://msd.wd5.myworkdayjobs.com/wday/cxs/msd/SearchJobs/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class BMSWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="bms", company_name="Bristol-Myers Squibb", careers_url="https://bristolmyerssquibb.wd5.myworkdayjobs.com/BMS", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://bristolmyerssquibb.wd5.myworkdayjobs.com/wday/cxs/bristolmyerssquibb/BMS/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class AmgenWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="amgen", company_name="Amgen", careers_url="https://amgen.wd1.myworkdayjobs.com/Careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://amgen.wd1.myworkdayjobs.com/wday/cxs/amgen/Careers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class BiogenWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="biogen", company_name="Biogen", careers_url="https://biibhr.wd3.myworkdayjobs.com/external", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://biibhr.wd3.myworkdayjobs.com/wday/cxs/biibhr/external/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class ThermoFisherWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="thermofisher", company_name="Thermo Fisher", careers_url="https://thermofisher.wd5.myworkdayjobs.com/ThermoFisherCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://thermofisher.wd5.myworkdayjobs.com/wday/cxs/thermofisher/ThermoFisherCareers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class CardinalHealthWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="cardinalhealth", company_name="Cardinal Health", careers_url="https://cardinalhealth.wd1.myworkdayjobs.com/EXT", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://cardinalhealth.wd1.myworkdayjobs.com/wday/cxs/cardinalhealth/EXT/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class DaVitaWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="davita", company_name="DaVita", careers_url="https://davita.wd1.myworkdayjobs.com/DKC_External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://davita.wd1.myworkdayjobs.com/wday/cxs/davita/DKC_External/jobs"


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


# ---------------------------------------------------------------------------
# Energy & Industrial
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class ChevronWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="chevron", company_name="Chevron", careers_url="https://chevron.wd5.myworkdayjobs.com/jobs", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://chevron.wd5.myworkdayjobs.com/wday/cxs/chevron/jobs/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class CaterpillarWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="caterpillar", company_name="Caterpillar", careers_url="https://cat.wd5.myworkdayjobs.com/CaterpillarCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://cat.wd5.myworkdayjobs.com/wday/cxs/cat/CaterpillarCareers/jobs"


# GE split; this is the GE Aerospace tenant (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class GEWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="ge", company_name="General Electric", careers_url="https://geaerospace.wd5.myworkdayjobs.com/GE_ExternalSite", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://geaerospace.wd5.myworkdayjobs.com/wday/cxs/geaerospace/GE_ExternalSite/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class DuPontWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="dupont", company_name="DuPont", careers_url="https://dupont.wd5.myworkdayjobs.com/Jobs", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://dupont.wd5.myworkdayjobs.com/wday/cxs/dupont/Jobs/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class DowWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="dow", company_name="Dow Chemical", careers_url="https://dow.wd1.myworkdayjobs.com/ExternalCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://dow.wd1.myworkdayjobs.com/wday/cxs/dow/ExternalCareers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class AppliedMaterialsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="appliedmaterials", company_name="Applied Materials", careers_url="https://amat.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://amat.wd1.myworkdayjobs.com/wday/cxs/amat/External/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class ConocoPhillipsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="conocophillips", company_name="ConocoPhillips", careers_url="https://conocophillips.wd1.myworkdayjobs.com/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://conocophillips.wd1.myworkdayjobs.com/wday/cxs/conocophillips/External/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class MarathonWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="marathon", company_name="Marathon Petroleum", careers_url="https://mpc.wd1.myworkdayjobs.com/MPCCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://mpc.wd1.myworkdayjobs.com/wday/cxs/mpc/MPCCareers/jobs"


@ScraperRegistry.register(category="enterprise")
class ThreeMWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="3m", company_name="3M Company", careers_url="https://3m.wd1.myworkdayjobs.com/Search", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://3m.wd1.myworkdayjobs.com/wday/cxs/3m/search/jobs"


# ---------------------------------------------------------------------------
# Consumer & Food
# ---------------------------------------------------------------------------

# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class PGWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="pg", company_name="Procter & Gamble", careers_url="https://pg.wd5.myworkdayjobs.com/1000", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://pg.wd5.myworkdayjobs.com/wday/cxs/pg/1000/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class KimberlyClarkWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="kimberlyclark", company_name="Kimberly-Clark", careers_url="https://kimberlyclark.wd1.myworkdayjobs.com/GLOBAL", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://kimberlyclark.wd1.myworkdayjobs.com/wday/cxs/kimberlyclark/GLOBAL/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class TysonWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="tyson", company_name="Tyson Foods", careers_url="https://tysonfoods.wd5.myworkdayjobs.com/TSN", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://tysonfoods.wd5.myworkdayjobs.com/wday/cxs/tysonfoods/TSN/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class MondelezWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="mondelez", company_name="Mondelez", careers_url="https://wd3.myworkdaysite.com/recruiting/mdlz/External", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://wd3.myworkdaysite.com/wday/cxs/mdlz/External/jobs"
    SITE_URL = "https://wd3.myworkdaysite.com/recruiting/mdlz/External"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class SmuckerWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="smucker", company_name="J.M. Smucker", careers_url="https://smucker.wd5.myworkdayjobs.com/US_External_Careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://smucker.wd5.myworkdayjobs.com/wday/cxs/smucker/US_External_Careers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class USFoodsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="usfoods", company_name="US Foods", careers_url="https://usfoods.wd1.myworkdayjobs.com/usfoodscareersExternal", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://usfoods.wd1.myworkdayjobs.com/wday/cxs/usfoods/usfoodscareersExternal/jobs"


# ---------------------------------------------------------------------------
# Transportation & Logistics
# ---------------------------------------------------------------------------

# Site name fixed (verified 2026-09-29) - FedEx Express Latin America site only; US site not found
@ScraperRegistry.register(category="enterprise")
class FedExWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="fedex", company_name="FedEx", careers_url="https://fedex.wd1.myworkdayjobs.com/FXE-LAC_External_Career_Site", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://fedex.wd1.myworkdayjobs.com/wday/cxs/fedex/FXE-LAC_External_Career_Site/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class SouthwestWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="southwest", company_name="Southwest Airlines", careers_url="https://swa.wd1.myworkdayjobs.com/external", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://swa.wd1.myworkdayjobs.com/wday/cxs/swa/external/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class JBHuntWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="jbhunt", company_name="J.B. Hunt", careers_url="https://jbhunt.wd501.myworkdayjobs.com/Careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://jbhunt.wd501.myworkdayjobs.com/wday/cxs/jbhunt/Careers/jobs"


# ---------------------------------------------------------------------------
# Telecom
# ---------------------------------------------------------------------------

# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class ATTWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="att", company_name="AT&T", careers_url="https://att.wd1.myworkdayjobs.com/ATTGeneral", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://att.wd1.myworkdayjobs.com/wday/cxs/att/ATTGeneral/jobs"


# ---------------------------------------------------------------------------
# Real Estate & Construction
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# European / Global
# ---------------------------------------------------------------------------

# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class UnileverWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="unilever", company_name="Unilever", careers_url="https://unilever.wd3.myworkdayjobs.com/Unilever_Experienced_Professionals", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://unilever.wd3.myworkdayjobs.com/wday/cxs/unilever/Unilever_Experienced_Professionals/jobs"


# Not Workday: moved to SmartRecruiters 'BoschGroup' (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class BoschWorkdayScraper(SmartRecruitersMixin, HTTPScraper):
    config = ScraperConfig(company_slug="bosch", company_name="Bosch", careers_url="https://jobs.bosch.com", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://api.smartrecruiters.com/v1/companies/BoschGroup/postings"
    COMPANY_ID = "BoschGroup"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class PhilipsWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="philips", company_name="Philips", careers_url="https://philips.wd3.myworkdayjobs.com/jobs-and-careers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://philips.wd3.myworkdayjobs.com/wday/cxs/philips/jobs-and-careers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class ShellWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="shell", company_name="Shell", careers_url="https://shell.wd3.myworkdayjobs.com/ShellCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://shell.wd3.myworkdayjobs.com/wday/cxs/shell/ShellCareers/jobs"


# Site name fixed (verified 2026-09-29)
@ScraperRegistry.register(category="enterprise")
class BPWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(company_slug="bp", company_name="BP", careers_url="https://bpinternational.wd3.myworkdayjobs.com/bpCareers", scraper_type=ScraperType.HTTP, rate_limit=30, max_pages=20)
    API_URL = "https://bpinternational.wd3.myworkdayjobs.com/wday/cxs/bpinternational/bpCareers/jobs"

