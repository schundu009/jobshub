"""Workday-based enterprise company scrapers with hybrid HTTP/Playwright approach."""
from scrapers.base import PlaywrightScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime
import asyncio
import httpx


class WorkdayHybridMixin:
    """
    Hybrid Workday scraper - tries HTTP API first, falls back to Playwright.

    Workday sites have a JSON API at /wday/cxs/{tenant}/{path}/jobs but many
    companies have API protections. For those, we use Playwright browser automation.
    """


# Alias for backwards compatibility
WorkdayPlaywrightMixin = WorkdayHybridMixin

    async def scrape(self) -> ScrapeResult:
        """Try HTTP API first, fall back to Playwright if needed."""
        # First try the fast HTTP API approach
        result = await self._try_http_api()
        if result.success and result.jobs_found > 0:
            return result

        # Fall back to Playwright browser automation
        self.logger.info(f"API returned 0 jobs for {self.config.company_name}, trying Playwright")
        return await self._try_playwright()

    async def _try_http_api(self) -> ScrapeResult:
        """Try to scrape using Workday's HTTP API."""
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 50

        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                payload = {"limit": limit, "offset": offset, "searchText": ""}

                try:
                    response = await client.post(self.API_URL, json=payload)
                    if response.status_code != 200:
                        self.logger.debug(f"API returned {response.status_code}")
                        break
                    data = response.json()
                except Exception as e:
                    self.logger.debug(f"API request failed: {e}")
                    break

                if not data:
                    break

                jobs = data.get("jobPostings", [])
                total = data.get("total", 0)

                if not jobs:
                    break

                for job in jobs:
                    parsed = self._parse_api_job(job)
                    if parsed:
                        all_jobs.append(parsed)

                if len(jobs) < limit:
                    break
                offset += limit
                if offset >= min(total, 1000):
                    break

        if all_jobs:
            self.logger.info(f"HTTP API: Found {len(all_jobs)} jobs for {self.config.company_name}")
        return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

    async def _try_playwright(self) -> ScrapeResult:
        """Scrape using Playwright browser automation."""
        all_jobs: List[ScrapedJob] = []

        page = await self.get_page()
        try:
            await page.goto(self.BASE_URL, wait_until="domcontentloaded", timeout=30000)

            # Wait for the page to stabilize
            await asyncio.sleep(2)

            # Try multiple selector strategies for job listings
            selectors = [
                '[data-automation-id="jobItem"]',
                'li[data-automation-id]',
                'article[data-automation-id]',
                'section[data-automation-id="jobResults"] li',
                '[role="listitem"]',
            ]

            job_elements = []
            for selector in selectors:
                try:
                    await page.wait_for_selector(selector, timeout=5000)
                    job_elements = await page.query_selector_all(selector)
                    if job_elements:
                        self.logger.debug(f"Found {len(job_elements)} elements with selector: {selector}")
                        break
                except:
                    continue

            if not job_elements:
                # Try scrolling to trigger lazy loading
                for _ in range(3):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(1)

                # Try selectors again
                for selector in selectors:
                    job_elements = await page.query_selector_all(selector)
                    if job_elements:
                        break

            if not job_elements:
                self.logger.info(f"No job elements found on {self.BASE_URL}")
                return ScrapeResult(success=True, jobs=[], jobs_found=0, error_message=None)

            # Parse each job element
            for element in job_elements[:100]:  # Limit to 100 jobs
                job = await self._parse_playwright_job(element, page)
                if job:
                    all_jobs.append(job)

            self.logger.info(f"Playwright: Found {len(all_jobs)} jobs for {self.config.company_name}")
            return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

        except Exception as e:
            self.logger.error(f"Playwright error for {self.config.company_name}: {e}")
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message=str(e))
        finally:
            await self.release_page(page)

    def _parse_api_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Parse a job from Workday API response."""
        try:
            title = raw.get("title", "")
            if not title:
                return None

            bullet_fields = raw.get("bulletFields", [])
            job_id = bullet_fields[0] if bullet_fields else ""
            location = raw.get("locationsText", "")

            posted_on = raw.get("postedOn", "")
            posted_date = None
            if posted_on:
                try:
                    posted_date = datetime.strptime(posted_on, "%Y-%m-%d")
                except:
                    pass

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
            self.logger.debug(f"Error parsing API job: {e}")
            return None

    async def _parse_playwright_job(self, element, page) -> Optional[ScrapedJob]:
        """Parse a job from Playwright element."""
        try:
            # Try to get title from various possible selectors
            title_selectors = [
                'a[data-automation-id="jobTitle"]',
                'h3 a', 'h2 a', 'a[href*="/job/"]',
                '[data-automation-id="jobTitle"]',
            ]

            title = ""
            job_url = ""
            for sel in title_selectors:
                title_el = await element.query_selector(sel)
                if title_el:
                    title = await title_el.text_content()
                    href = await title_el.get_attribute("href")
                    if href:
                        if href.startswith("http"):
                            job_url = href
                        else:
                            base = self.BASE_URL.split('.com')[0] + '.com'
                            job_url = f"{base}{href}"
                    break

            if not title:
                # Try getting any text content as fallback
                title = await element.text_content()
                if title:
                    title = title.split('\n')[0][:100]  # First line, max 100 chars

            if not title or len(title.strip()) < 3:
                return None

            # Try to get location
            location = ""
            location_selectors = [
                '[data-automation-id="locations"]',
                '[data-automation-id="location"]',
                'dd', 'span[class*="location"]',
            ]
            for sel in location_selectors:
                loc_el = await element.query_selector(sel)
                if loc_el:
                    location = await loc_el.text_content()
                    if location:
                        break

            # Extract job ID from URL
            job_id = ""
            if "/job/" in job_url:
                job_id = job_url.split("/job/")[-1].split("/")[0].split("?")[0]

            return ScrapedJob(
                title=title.strip(),
                location=location.strip() if location else "",
                job_url=job_url,
                external_job_id=job_id,
            )
        except Exception as e:
            self.logger.debug(f"Error parsing Playwright job: {e}")
            return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Required by base class but we use custom methods."""
        return self._parse_api_job(raw)


# Company configurations: (slug, name, tenant, subdomain, job_site_path)
# Verified Workday URLs - January 2025
WORKDAY_COMPANIES = [
    # Retail
    ("walmart", "Walmart", "walmart", "wd5", "WalmartExternal"),
    ("target", "Target", "target", "wd5", "targetcareers"),
    ("homedepot", "Home Depot", "homedepot", "wd5", "CareerDepot"),
    ("kohls", "Kohl's", "kohls", "wd5", "External"),
    ("nordstrom", "Nordstrom", "nordstrom", "wd5", "External"),
    ("gap", "Gap Inc.", "gap", "wd5", "External"),
    ("lululemon", "Lululemon", "lululemon", "wd1", "External"),

    # Tech & Media
    ("broadcom", "Broadcom", "broadcom", "wd1", "External_Career"),
    ("netflix", "Netflix", "netflix", "wd1", "Netflix"),
    ("hp", "HP Inc.", "hp", "wd5", "External"),
    ("westerndigital", "Western Digital", "westerndigital", "wd5", "External"),
    ("motorolasolutions", "Motorola Solutions", "motorolasolutions", "wd5", "External"),
    ("ebay", "eBay", "ebay", "wd5", "External"),
    ("equinix", "Equinix", "equinix", "wd5", "External"),

    # Consulting & Professional Services
    ("accenture", "Accenture", "accenture", "wd103", "AccentureCareers"),
    ("pwc", "PwC", "pwc", "wd3", "Global_Experienced_Careers"),
    ("deloitte", "Deloitte Ireland", "deloitteie", "wd3", "Experienced_Professionals"),
    ("cognizant", "Cognizant", "cognizant", "wd1", "External"),
    ("capgemini", "Capgemini", "capgemini", "wd3", "External"),
    ("dxc", "DXC Technology", "dxc", "wd1", "External"),
    ("boozallen", "Booz Allen Hamilton", "boozallen", "wd1", "External"),
    ("jll", "Jones Lang LaSalle", "jll", "wd1", "External"),

    # Banking & Finance
    ("wellsfargo", "Wells Fargo", "wf", "wd1", "WellsFargoJobs"),
    ("bankofamerica", "Bank of America", "ghr", "wd1", "Lateral-US"),
    ("morganstanley", "Morgan Stanley", "ms", "wd5", "External"),
    ("citi", "Citibank", "citi", "wd5", "2"),
    ("blackrock", "BlackRock", "blackrock", "wd1", "BlackRock_Professional"),
    ("mastercard", "Mastercard", "mastercard", "wd1", "Campus"),
    ("pnc", "PNC Bank", "pnc", "wd5", "External"),
    ("schwab", "Charles Schwab", "schwab", "wd1", "External"),
    ("discover", "Discover Financial", "discover", "wd5", "External"),
    ("fifththird", "Fifth Third Bank", "fifththird", "wd5", "External"),
    ("keybank", "KeyBank", "keybank", "wd5", "External"),
    ("mtbank", "M&T Bank", "mtbank", "wd5", "External"),
    ("regions", "Regions Bank", "regions", "wd5", "External"),
    ("huntington", "Huntington Bank", "huntington", "wd5", "External"),
    ("fiserv", "Fiserv", "fiserv", "wd5", "External"),
    ("franklintempleton", "Franklin Templeton", "franklintempleton", "wd5", "External"),
    ("freddiemac", "Freddie Mac", "freddiemac", "wd1", "External"),
    ("fanniemae", "Fannie Mae", "fanniemae", "wd5", "External"),
    ("mmc", "Marsh & McLennan", "mmc", "wd1", "External"),

    # Insurance
    ("travelers", "Travelers", "travelers", "wd5", "External"),
    ("hartford", "Hartford Insurance", "hartford", "wd5", "External"),
    ("humana", "Humana", "humana", "wd5", "External"),
    ("prudential", "Prudential", "prudential", "wd5", "External"),
    ("massmutual", "MassMutual", "massmutual", "wd5", "External"),

    # Pharma & Healthcare
    ("pfizer", "Pfizer", "pfizer", "wd1", "PfizerCareers"),
    ("abbott", "Abbott", "abbott", "wd5", "abbottcareers"),
    ("merck", "Merck", "merck", "wd5", "External"),
    ("bms", "Bristol-Myers Squibb", "bms", "wd5", "External"),
    ("amgen", "Amgen Inc.", "amgen", "wd5", "External"),
    ("biogen", "Biogen", "biogen", "wd5", "External"),
    ("thermofisher", "Thermo Fisher", "thermofisher", "wd5", "External"),
    ("cardinalhealth", "Cardinal Health", "cardinalhealth", "wd1", "External"),
    ("davita", "DaVita", "davita", "wd1", "External"),
    ("optum", "Optum", "optum", "wd5", "External"),
    ("walgreens", "Walgreens", "walgreens", "wd5", "External"),

    # Defense & Aerospace
    ("northropgrumman", "Northrop Grumman", "ngc", "wd1", "Northrop_Grumman_External_Site"),
    ("rtx", "RTX Corporation", "globalhr", "wd5", "REC_RTX_Ext_Gateway"),
    ("leidos", "Leidos", "leidos", "wd5", "External"),

    # Energy & Industrial
    ("chevron", "Chevron", "chevron", "wd5", "jobs"),
    ("exxonmobil", "ExxonMobil", "exxonmobil", "wd5", "External"),
    ("caterpillar", "Caterpillar", "caterpillar", "wd5", "External"),
    ("ge", "General Electric", "ge", "wd5", "External"),
    ("dupont", "DuPont", "dupont", "wd5", "External"),
    ("dow", "Dow Chemical", "dow", "wd5", "External"),
    ("appliedmaterials", "Applied Materials", "appliedmaterials", "wd5", "External"),
    ("conocophillips", "ConocoPhillips", "conocophillips", "wd5", "External"),
    ("marathon", "Marathon Petroleum", "marathon", "wd5", "External"),
    ("3m", "3M Company", "3m", "wd1", "Search"),

    # Consumer & Food
    ("pg", "Procter & Gamble", "pg", "wd5", "External"),
    ("kimberlyclark", "Kimberly-Clark", "kimberlyclark", "wd5", "External"),
    ("tyson", "Tyson Foods", "tyson", "wd5", "External"),
    ("chipotle", "Chipotle", "chipotle", "wd1", "External"),
    ("mondelez", "Mondelez", "mondelez", "wd1", "External"),
    ("smucker", "J.M. Smucker", "smucker", "wd1", "External"),
    ("usfoods", "US Foods", "usfoods", "wd5", "External"),

    # Transportation & Logistics
    ("fedex", "FedEx", "fedex", "wd1", "FXE_External"),
    ("southwest", "Southwest Airlines", "southwest", "wd5", "External"),
    ("jbhunt", "J.B. Hunt", "jbhunt", "wd5", "External"),

    # Telecom
    ("att", "AT&T", "att", "wd5", "External"),

    # Real Estate & Construction
    ("lennar", "Lennar Homes", "lennar", "wd1", "External"),
    ("tollbrothers", "Toll Brothers", "tollbrothers", "wd1", "External"),

    # European/Global
    ("vodafone", "Vodafone", "vodafone", "wd3", "External"),
    ("unilever", "Unilever", "unilever", "wd3", "External"),
    ("siemens", "Siemens", "siemens", "wd1", "External"),
    ("bosch", "Bosch", "bosch", "wd1", "External"),
    ("philips", "Philips", "philips", "wd3", "External"),
    ("shell", "Shell", "shell", "wd3", "External"),
    ("bp", "BP", "bp", "wd1", "External"),
    ("dhl", "DHL", "dhl", "wd3", "External"),
    ("bae", "BAE Systems", "bae", "wd1", "External"),
]


def create_workday_scraper(slug: str, name: str, tenant: str, subdomain: str, job_site_path: str):
    """Factory function to create Workday scraper classes with hybrid HTTP/Playwright support."""
    base_url = f"https://{tenant}.{subdomain}.myworkdayjobs.com/{job_site_path}"
    api_url = f"https://{tenant}.{subdomain}.myworkdayjobs.com/wday/cxs/{tenant}/{job_site_path}/jobs"

    class WorkdayScraper(WorkdayHybridMixin, PlaywrightScraper):
        config = ScraperConfig(
            company_slug=slug,
            company_name=name,
            careers_url=base_url,
            scraper_type=ScraperType.PLAYWRIGHT,  # Use Playwright to enable browser fallback
            rate_limit=15,
            max_pages=10,
            page_timeout=45,
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
