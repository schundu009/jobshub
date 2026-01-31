"""Workday-based enterprise company scrapers using HTTP API."""
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


class WorkdayAPIMixin:
    """Mixin for Workday job board scraping using HTTP API."""

    async def scrape(self) -> ScrapeResult:
        """Scrape Workday careers using their JSON API."""
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 50

        while True:
            payload = {"limit": limit, "offset": offset, "searchText": ""}

            try:
                data = await self.fetch_json(self.API_URL, method="POST", json=payload)
            except Exception as e:
                self.logger.error(f"Error fetching jobs from {self.API_URL}: {e}")
                if all_jobs:
                    # Return what we have so far
                    break
                return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message=str(e))

            if not data:
                self.logger.warning(f"No data returned from {self.API_URL}")
                break

            jobs = data.get("jobPostings", [])
            total = data.get("total", 0)

            if not jobs:
                if offset == 0:
                    self.logger.info(f"No jobs found for {self.config.company_name}")
                break

            for job in jobs:
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

            self.logger.debug(f"Fetched {len(jobs)} jobs (offset={offset}, total={total})")

            if len(jobs) < limit:
                break
            offset += limit
            if offset >= min(total, 1000):  # Cap at 1000 jobs
                break

        self.logger.info(f"Scraped {len(all_jobs)} jobs from {self.config.company_name}")
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse a job from Workday API response."""
        try:
            title = raw.get("title", "")
            if not title:
                return None

            # Extract job ID from bulletFields (usually first item)
            bullet_fields = raw.get("bulletFields", [])
            job_id = bullet_fields[0] if bullet_fields else ""

            # Location
            location = raw.get("locationsText", "")

            # Posted date
            posted_on = raw.get("postedOn", "")
            posted_date = None
            if posted_on:
                try:
                    posted_date = datetime.strptime(posted_on, "%Y-%m-%d")
                except:
                    pass

            # Build job URL from external path
            external_path = raw.get("externalPath", "")
            job_url = f"{self.BASE_URL}{external_path}" if external_path else ""

            return ScrapedJob(
                title=title.strip(),
                location=location.strip() if location else "",
                job_url=job_url,
                external_job_id=job_id,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.debug(f"Error parsing job: {e}")
            return None


# Company configurations: (slug, name, tenant, subdomain, job_site_path)
# Verified Workday URLs from web research
WORKDAY_COMPANIES = [
    # Verified working configurations
    ("walmart", "Walmart", "walmart", "wd5", "WalmartExternal"),
    ("target", "Target", "target", "wd5", "targetcareers"),
    ("netflix", "Netflix", "netflix", "wd1", "Netflix"),
    # ("adobe", "Adobe", "adobe", "wd5", "external_experienced"),  # Has dedicated scraper
    ("accenture", "Accenture", "accenture", "wd103", "AccentureCareers"),
    ("pwc", "PwC", "pwc", "wd3", "Global_Experienced_Careers"),
    ("deloitte", "Deloitte Ireland", "deloitteie", "wd3", "Experienced_Professionals"),

    # Fortune 500 / Enterprise companies
    ("3m", "3M Company", "3m", "wd1", "External"),
    ("abbvie", "AbbVie Inc.", "abbvie", "wd5", "External"),
    ("activision", "Activision Publishing", "activision", "wd5", "External"),
    ("aecom", "AECOM", "aecom", "wd1", "External"),
    ("alcoa", "Alcoa Corp", "alcoa", "wd1", "External"),
    ("amgen", "Amgen Inc.", "amgen", "wd5", "External"),
    ("analogdevices", "Analog Devices", "analogdevices", "wd1", "External"),
    ("appliedmaterials", "Applied Materials", "appliedmaterials", "wd5", "External"),
    ("arrowelectronics", "Arrow Electronics", "arrowelectronics", "wd1", "External"),
    ("assurant", "Assurant", "assurant", "wd1", "External"),
    ("att", "AT&T", "att", "wd5", "External"),
    ("avisbudget", "Avis Budget", "avisbudget", "wd1", "External"),
    ("bankofamerica", "Bank of America", "bankofamerica", "wd1", "External"),
    ("bd", "Becton Dickinson", "bd", "wd1", "External"),
    ("biogen", "Biogen", "biogen", "wd5", "External"),
    ("blackrock", "BlackRock", "blackrock", "wd1", "External"),
    ("boozallen", "Booz Allen Hamilton", "boozallen", "wd1", "External"),
    ("borgwarner", "BorgWarner", "borgwarner", "wd1", "External"),
    ("bms", "Bristol-Myers Squibb", "bms", "wd5", "External"),
    ("burlington", "Burlington", "burlington", "wd1", "External"),
    ("cardinalhealth", "Cardinal Health", "cardinalhealth", "wd1", "External"),
    ("carmax", "CarMax", "carmax", "wd1", "External"),
    ("caterpillar", "Caterpillar", "caterpillar", "wd5", "External"),
    ("cfindustries", "CF Industries", "cfindustries", "wd1", "External"),
    ("schwab", "Charles Schwab", "schwab", "wd1", "External"),
    ("chevron", "Chevron", "chevron", "wd5", "External"),
    ("citi", "Citibank", "citi", "wd5", "External"),
    ("chipotle", "Chipotle", "chipotle", "wd1", "External"),
    ("cognizant", "Cognizant", "cognizant", "wd1", "External"),
    ("conocophillips", "ConocoPhillips", "conocophillips", "wd5", "External"),
    ("constellationbrands", "Constellation Brands", "constellationbrands", "wd1", "External"),
    ("davita", "DaVita", "davita", "wd1", "External"),
    ("discover", "Discover Financial", "discover", "wd5", "External"),
    ("diamondback", "Diamondback Energy", "diamondback", "wd1", "External"),
    ("dollartree", "Dollar Tree", "dollartree", "wd1", "External"),
    ("dupont", "DuPont", "dupont", "wd5", "External"),
    ("dxc", "DXC Technology", "dxc", "wd1", "External"),
    ("ebay", "eBay", "ebay", "wd5", "External"),
    ("equinix", "Equinix", "equinix", "wd5", "External"),
    ("eversource", "Eversource Energy", "eversource", "wd1", "External"),
    ("exxonmobil", "ExxonMobil", "exxonmobil", "wd5", "External"),
    ("freddiemac", "Freddie Mac", "freddiemac", "wd1", "External"),
    ("fanniemae", "Fannie Mae", "fanniemae", "wd5", "External"),
    ("fedex", "FedEx", "fedex", "wd5", "External"),
    ("fidelitynational", "Fidelity National", "fidelitynational", "wd1", "External"),
    ("fifththird", "Fifth Third Bank", "fifththird", "wd5", "External"),
    ("firstcitizens", "First Citizens Bank", "firstcitizens", "wd1", "External"),
    ("fiserv", "Fiserv", "fiserv", "wd5", "External"),
    ("fortunebrands", "Fortune Brands", "fortunebrands", "wd1", "External"),
    ("franklintempleton", "Franklin Templeton", "franklintempleton", "wd5", "External"),
    ("ge", "General Electric", "ge", "wd5", "External"),
    ("genuineparts", "Genuine Parts Company", "genuineparts", "wd1", "External"),
    ("hartford", "Hartford Insurance", "hartford", "wd5", "External"),
    ("henryschein", "Henry Schein", "henryschein", "wd1", "External"),
    # ("hpe", "Hewlett Packard Enterprise", "hpe", "wd5", "External"),  # Has dedicated scraper
    ("homedepot", "Home Depot", "homedepot", "wd5", "External"),
    ("hp", "HP Inc.", "hp", "wd5", "External"),
    ("humana", "Humana", "humana", "wd5", "External"),
    ("huntsman", "Huntsman", "huntsman", "wd1", "External"),
    ("itw", "Illinois Tool Works", "itw", "wd1", "External"),
    # ("ibm", "IBM", "ibm", "wd1", "External"),  # Has dedicated scraper
    ("iff", "International Flavors & Fragrances", "iff", "wd1", "External"),
    ("interpublic", "Interpublic Group", "interpublic", "wd1", "External"),
    ("intuit", "Intuit", "intuit", "wd5", "External"),
    ("iqvia", "IQVIA", "iqvia", "wd1", "External"),
    ("jbhunt", "J.B. Hunt", "jbhunt", "wd5", "External"),
    ("smucker", "J.M. Smucker", "smucker", "wd1", "External"),
    ("jabil", "Jabil", "jabil", "wd5", "External"),
    ("jll", "Jones Lang LaSalle", "jll", "wd1", "External"),
    ("keybank", "KeyBank", "keybank", "wd5", "External"),
    ("kimberlyclark", "Kimberly-Clark", "kimberlyclark", "wd5", "External"),
    ("kohls", "Kohl's", "kohls", "wd5", "External"),
    ("landolakes", "Land O'Lakes", "landolakes", "wd1", "External"),
    ("leidos", "Leidos", "leidos", "wd5", "External"),
    ("lennar", "Lennar Homes", "lennar", "wd1", "External"),
    ("lithia", "Lithia Motors", "lithia", "wd1", "External"),
    ("livenation", "Live Nation", "livenation", "wd1", "External"),
    ("lpl", "LPL Financial", "lpl", "wd1", "External"),
    ("lululemon", "Lululemon", "lululemon", "wd1", "External"),
    ("mtbank", "M&T Bank", "mtbank", "wd5", "External"),
    ("marathon", "Marathon Petroleum", "marathon", "wd5", "External"),
    ("mmc", "Marsh & McLennan", "mmc", "wd1", "External"),
    ("masco", "Masco Corporation", "masco", "wd1", "External"),
    ("massmutual", "MassMutual", "massmutual", "wd5", "External"),
    ("mastercard", "Mastercard", "mastercard", "wd1", "External"),
    ("merck", "Merck", "merck", "wd5", "External"),
    ("mgm", "MGM Resorts", "mgm", "wd1", "External"),
    ("mondelez", "Mondelez", "mondelez", "wd1", "External"),
    ("morganstanley", "Morgan Stanley", "morganstanley", "wd5", "External"),
    ("motorolasolutions", "Motorola Solutions", "motorolasolutions", "wd5", "External"),
    ("ncr", "NCR Voyix", "ncr", "wd1", "External"),
    ("nordstrom", "Nordstrom", "nordstrom", "wd5", "External"),
    # ("nvidia", "NVIDIA", "nvidia", "wd5", "External"),  # Has dedicated scraper
    ("oshkosh", "Oshkosh Corporation", "oshkosh", "wd1", "External"),
    ("otis", "Otis Elevator", "otis", "wd5", "External"),
    ("owensminor", "Owens & Minor", "owensminor", "wd1", "External"),
    ("pacificlife", "Pacific Life", "pacificlife", "wd1", "External"),
    ("pfizer", "Pfizer", "pfizer", "wd5", "External"),
    ("pnc", "PNC Bank", "pnc", "wd5", "External"),
    ("polaris", "Polaris Industries", "polaris", "wd1", "External"),
    ("raymondjames", "Raymond James", "raymondjames", "wd1", "External"),
    ("regions", "Regions Bank", "regions", "wd5", "External"),
    ("rga", "Reinsurance Group", "rga", "wd5", "External"),
    ("riteaid", "Rite Aid", "riteaid", "wd1", "External"),
    ("rtx", "RTX Corporation", "rtx", "wd5", "External"),
    ("ryder", "Ryder", "ryder", "wd1", "External"),
    ("sonoco", "Sonoco Products", "sonoco", "wd1", "External"),
    ("southwest", "Southwest Airlines", "southwest", "wd5", "External"),
    ("spartannash", "SpartanNash", "spartannash", "wd1", "External"),
    ("stanleyblackdecker", "Stanley Black & Decker", "stanleyblackdecker", "wd1", "External"),
    ("taylormorrison", "Taylor Morrison", "taylormorrison", "wd1", "External"),
    ("dow", "Dow Chemical", "dow", "wd5", "External"),
    ("gap", "Gap Inc.", "gap", "wd5", "External"),
    ("goodyear", "Goodyear", "goodyear", "wd1", "External"),
    ("guardianlife", "Guardian Life", "guardianlife", "wd5", "External"),
    ("huntington", "Huntington Bank", "huntington", "wd5", "External"),
    ("mosaic", "Mosaic Company", "mosaic", "wd1", "External"),
    ("pg", "Procter & Gamble", "pg", "wd5", "External"),
    ("prudential", "Prudential", "prudential", "wd5", "External"),
    ("travelers", "Travelers", "travelers", "wd5", "External"),
    ("thermofisher", "Thermo Fisher", "thermofisher", "wd5", "External"),
    ("thrivent", "Thrivent", "thrivent", "wd1", "External"),
    ("tollbrothers", "Toll Brothers", "tollbrothers", "wd1", "External"),
    ("tyson", "Tyson Foods", "tyson", "wd5", "External"),
    ("ufp", "UFP Industries", "ufp", "wd1", "External"),
    ("unum", "Unum Group", "unum", "wd1", "External"),
    ("usfoods", "US Foods", "usfoods", "wd5", "External"),
    ("vf", "VF Corporation", "vf", "wd1", "External"),
    # ("visa", "Visa", "visa", "wd5", "External"),  # Has dedicated scraper
    ("vistra", "Vistra", "vistra", "wd1", "External"),
    ("wellsfargo", "Wells Fargo", "wellsfargo", "wd5", "External"),
    ("westerndigital", "Western Digital", "westerndigital", "wd5", "External"),
    ("wabtec", "Westinghouse Air Brake", "wabtec", "wd5", "External"),
    ("williams", "Williams Companies", "williams", "wd1", "External"),
    ("worldfuel", "World Fuel Services", "worldfuel", "wd1", "External"),
    ("zoetis", "Zoetis", "zoetis", "wd5", "External"),

    # Additional enterprise companies
    ("airbnb", "Airbnb", "airbnb", "wd5", "Airbnb"),
    ("capgemini", "Capgemini", "capgemini", "wd3", "External"),
    ("vodafone", "Vodafone", "vodafone", "wd3", "External"),
    ("unilever", "Unilever", "unilever", "wd3", "External"),
    ("siemens", "Siemens", "siemens", "wd1", "External"),
    ("bosch", "Bosch", "bosch", "wd1", "External"),
    ("philips", "Philips", "philips", "wd3", "External"),
    ("shell", "Shell", "shell", "wd3", "External"),
    ("bp", "BP", "bp", "wd1", "External"),
    ("dhl", "DHL", "dhl", "wd3", "External"),
    ("northropgrumman", "Northrop Grumman", "northropgrumman", "wd5", "External"),
    ("lockheedmartin", "Lockheed Martin", "lockheedmartin", "wd5", "External"),
    ("raytheon", "Raytheon", "raytheon", "wd5", "External"),
    ("bae", "BAE Systems", "bae", "wd1", "External"),
    ("walgreens", "Walgreens", "walgreens", "wd5", "External"),
    ("optum", "Optum", "optum", "wd5", "External"),
    ("tenethealth", "Tenet Healthcare", "tenethealth", "wd5", "External"),
    ("sodexo", "Sodexo", "sodexo", "wd1", "External"),
]


def create_workday_scraper(slug: str, name: str, tenant: str, subdomain: str, job_site_path: str):
    """Factory function to create Workday scraper classes using HTTP API."""
    base_url = f"https://{tenant}.{subdomain}.myworkdayjobs.com/{job_site_path}"
    api_url = f"https://{tenant}.{subdomain}.myworkdayjobs.com/wday/cxs/{tenant}/{job_site_path}/jobs"

    class WorkdayScraper(WorkdayAPIMixin, HTTPScraper):
        config = ScraperConfig(
            company_slug=slug,
            company_name=name,
            careers_url=base_url,
            scraper_type=ScraperType.HTTP,
            rate_limit=30,
            max_pages=20,
        )
        BASE_URL = base_url
        API_URL = api_url

    WorkdayScraper.__name__ = f"{slug.title().replace(' ', '')}Scraper"
    WorkdayScraper.__qualname__ = WorkdayScraper.__name__
    return WorkdayScraper


# Register all Workday scrapers
for company_config in WORKDAY_COMPANIES:
    slug, name, tenant, subdomain, job_site_path = company_config
    scraper_class = create_workday_scraper(slug, name, tenant, subdomain, job_site_path)
    ScraperRegistry.register(category="enterprise")(scraper_class)
