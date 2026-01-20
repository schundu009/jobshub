"""Workday-based enterprise company scrapers using Playwright."""
from scrapers.base import PlaywrightScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import asyncio
import re


class WorkdayPlaywrightMixin:
    """Mixin for Workday job board scraping using Playwright."""

    async def scrape(self) -> ScrapeResult:
        """Scrape Workday careers using Playwright browser automation."""
        all_jobs: List[ScrapedJob] = []

        page = await self.get_page()
        try:
            # Navigate to the careers page
            await page.goto(self.BASE_URL, wait_until="networkidle", timeout=30000)

            # Wait for job listings to load
            try:
                await page.wait_for_selector('[data-automation-id="jobItem"], .css-19uc56f, section[data-automation-id="jobResults"]', timeout=15000)
            except Exception:
                self.logger.info(f"No job listings found on {self.BASE_URL}")
                return ScrapeResult(success=True, jobs=[], jobs_found=0, error_message=None)

            # Scroll to load more jobs (Workday uses lazy loading)
            for _ in range(5):
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(1)

            # Extract job data from cards
            job_cards = await page.query_selector_all('[data-automation-id="jobItem"], li[class*="css-"]')

            for card in job_cards:
                job = await self._parse_job_card(card, page)
                if job:
                    all_jobs.append(job)

            # Fetch job details (description, posted date, salary) for each job
            jobs_to_fetch = all_jobs[:50]
            for i, job in enumerate(jobs_to_fetch):
                if job.job_url:
                    try:
                        details = await self._fetch_job_details(page, job.job_url)
                        if details:
                            if details.get('description'):
                                job.job_description = details['description']
                            if details.get('posted_date'):
                                job.posted_date = details['posted_date']
                            if details.get('salary_min'):
                                job.salary_min = details['salary_min']
                            if details.get('salary_max'):
                                job.salary_max = details['salary_max']
                        # Small delay to avoid rate limiting
                        if i < len(jobs_to_fetch) - 1:
                            await asyncio.sleep(0.5)
                    except Exception as e:
                        self.logger.debug(f"Error fetching details for {job.title}: {e}")

            return ScrapeResult(success=True, jobs=all_jobs, jobs_found=len(all_jobs), error_message=None)

        except Exception as e:
            self.logger.error(f"Error scraping {self.config.company_name}: {e}")
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message=str(e))
        finally:
            await self.release_page(page)

    async def _fetch_job_details(self, page, job_url: str) -> Optional[Dict[str, Any]]:
        """Fetch full job details (description, posted date, salary) from detail page."""
        result = {
            'description': None,
            'posted_date': None,
            'salary_min': None,
            'salary_max': None
        }

        try:
            await page.goto(job_url, wait_until="networkidle", timeout=20000)

            # Wait for job content to load
            await page.wait_for_selector('[data-automation-id="jobPostingDescription"], .job-description, [class*="jobDescription"]', timeout=10000)

            # === Extract Job Description ===
            description_selectors = [
                '[data-automation-id="jobPostingDescription"]',
                '.job-description',
                '[class*="jobDescription"]',
                '[data-automation-id="job-posting-description"]',
                'div[class*="description"]'
            ]

            for selector in description_selectors:
                desc_el = await page.query_selector(selector)
                if desc_el:
                    description = await desc_el.inner_text()
                    if description and len(description) > 50:
                        result['description'] = description.strip()
                        break

            # === Extract Posted Date ===
            posted_date = await self._extract_posted_date(page)
            if posted_date:
                result['posted_date'] = posted_date

            # === Extract Salary ===
            salary_min, salary_max = await self._extract_salary(page, result.get('description', ''))
            if salary_min:
                result['salary_min'] = salary_min
            if salary_max:
                result['salary_max'] = salary_max

            return result
        except Exception as e:
            self.logger.debug(f"Error fetching details from {job_url}: {e}")
            return result

    async def _extract_posted_date(self, page) -> Optional[datetime]:
        """Extract posted date from Workday job detail page."""
        try:
            # Try multiple selectors for posted date
            date_selectors = [
                '[data-automation-id="postedOn"]',
                '[data-automation-id="posted-on"]',
                'dd[data-automation-id="time"]',
                '[class*="postedDate"]',
                '[class*="posted-date"]',
                'time[datetime]',
            ]

            for selector in date_selectors:
                date_el = await page.query_selector(selector)
                if date_el:
                    # Check for datetime attribute first
                    datetime_attr = await date_el.get_attribute('datetime')
                    if datetime_attr:
                        try:
                            return datetime.fromisoformat(datetime_attr.replace('Z', '+00:00').split('+')[0])
                        except:
                            pass

                    # Try text content
                    date_text = await date_el.inner_text()
                    if date_text:
                        parsed = self._parse_relative_date(date_text.strip())
                        if parsed:
                            return parsed

            # Try to find date in page content using regex
            page_content = await page.content()

            # Look for "Posted X days ago" pattern
            relative_patterns = [
                r'[Pp]osted\s+(\d+)\s+days?\s+ago',
                r'[Pp]osted\s+(\d+)\s+hours?\s+ago',
                r'[Pp]osted\s+today',
                r'[Pp]osted\s+yesterday',
            ]

            for pattern in relative_patterns:
                match = re.search(pattern, page_content)
                if match:
                    return self._parse_relative_date(match.group(0))

            # Look for actual date formats
            date_patterns = [
                r'(\d{4}-\d{2}-\d{2})',  # 2024-01-15
                r'(\d{1,2}/\d{1,2}/\d{4})',  # 1/15/2024
                r'([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4})',  # Jan 15, 2024
            ]

            for pattern in date_patterns:
                match = re.search(pattern, page_content)
                if match:
                    date_str = match.group(1)
                    for fmt in ['%Y-%m-%d', '%m/%d/%Y', '%b %d, %Y']:
                        try:
                            return datetime.strptime(date_str, fmt)
                        except:
                            continue

            return None
        except Exception as e:
            self.logger.debug(f"Error extracting posted date: {e}")
            return None

    def _parse_relative_date(self, text: str) -> Optional[datetime]:
        """Parse relative date strings like 'Posted 3 days ago'."""
        text = text.lower().strip()
        now = datetime.now()

        if 'today' in text:
            return now
        elif 'yesterday' in text:
            return now - timedelta(days=1)

        # "X days ago"
        days_match = re.search(r'(\d+)\s*days?\s*ago', text)
        if days_match:
            days = int(days_match.group(1))
            return now - timedelta(days=days)

        # "X hours ago"
        hours_match = re.search(r'(\d+)\s*hours?\s*ago', text)
        if hours_match:
            return now

        # "X weeks ago"
        weeks_match = re.search(r'(\d+)\s*weeks?\s*ago', text)
        if weeks_match:
            weeks = int(weeks_match.group(1))
            return now - timedelta(weeks=weeks)

        # "X months ago"
        months_match = re.search(r'(\d+)\s*months?\s*ago', text)
        if months_match:
            months = int(months_match.group(1))
            return now - timedelta(days=months * 30)

        return None

    async def _extract_salary(self, page, description: str = '') -> tuple:
        """Extract salary range from Workday job detail page."""
        salary_min = None
        salary_max = None

        try:
            # Try selectors for salary section
            salary_selectors = [
                '[data-automation-id="compensation"]',
                '[data-automation-id="salary"]',
                '[class*="salary"]',
                '[class*="compensation"]',
                '[class*="pay-range"]',
            ]

            salary_text = ""
            for selector in salary_selectors:
                salary_el = await page.query_selector(selector)
                if salary_el:
                    salary_text = await salary_el.inner_text()
                    if salary_text and '$' in salary_text:
                        break

            # If not found in specific element, search in description
            if not salary_text and description:
                salary_text = description

            # If still not found, get full page text
            if not salary_text or '$' not in salary_text:
                page_text = await page.inner_text('body')
                # Look for salary section
                salary_match = re.search(r'(?:salary|compensation|pay)[:\s]*([^\n]{10,100}\$[^\n]{0,100})', page_text, re.IGNORECASE)
                if salary_match:
                    salary_text = salary_match.group(1)

            # Parse salary from text
            if salary_text:
                salary_min, salary_max = self._parse_salary_text(salary_text)

        except Exception as e:
            self.logger.debug(f"Error extracting salary: {e}")

        return salary_min, salary_max

    def _parse_salary_text(self, text: str) -> tuple:
        """Parse salary range from text."""
        if not text:
            return None, None

        # Normalize text - remove commas but preserve structure
        text_clean = text.replace(',', '').replace('—', '-').replace('–', '-')

        # Salary patterns (order matters - more specific first)
        patterns = [
            # 152000 USD - 218500 USD (NVIDIA format)
            r'(\d{5,})\s*USD\s*[-–—]\s*(\d{5,})\s*USD',
            # $320000-$405000 USD or $128880-245160 USD
            r'\$\s*(\d+)(?:\.\d{2})?\s*[-–—]\s*\$?\s*(\d+)(?:\.\d{2})?\s*(?:USD|per year|annually)?',
            # $150K - $200K
            r'\$\s*(\d+)\s*[kK]\s*[-–—]\s*\$?\s*(\d+)\s*[kK]',
            # $150000 to $200000
            r'\$\s*(\d+)\s+to\s+\$?\s*(\d+)',
            # USD 150000 - 200000
            r'USD\s*(\d+)\s*[-–—]\s*(\d+)',
            # base salary range is X - Y
            r'base\s+salary\s+range\s+is\s+(\d{5,})\s*[-–—]\s*(\d{5,})',
            # Single salary: $150000 or 150000 USD
            r'\$\s*(\d{5,})',
            r'(\d{5,})\s*USD',
        ]

        for pattern in patterns:
            match = re.search(pattern, text_clean, re.IGNORECASE)
            if match:
                groups = match.groups()
                min_str = groups[0]
                max_str = groups[1] if len(groups) > 1 else None

                # Handle K notation (check the matched text itself)
                matched_text = match.group(0).lower()
                if 'k' in matched_text:
                    min_val = int(min_str) * 1000
                    max_val = int(max_str) * 1000 if max_str else None
                else:
                    min_val = int(min_str)
                    max_val = int(max_str) if max_str else None

                # Validate reasonable salary range (30k - 2M for tech)
                if 30000 <= min_val <= 2000000:
                    if max_val:
                        if max_val >= min_val and max_val <= 2000000:
                            return min_val, max_val
                        elif max_val < min_val:
                            return max_val, min_val  # Swap if reversed
                    else:
                        return min_val, None

        return None, None

    async def _parse_job_card(self, card, page) -> Optional[ScrapedJob]:
        """Parse a Workday job card element."""
        try:
            # Get job title
            title_el = await card.query_selector('a[data-automation-id="jobTitle"], h3 a, a[class*="css-"]')
            title = await title_el.text_content() if title_el else ""

            # Get job URL
            href = await title_el.get_attribute("href") if title_el else ""
            if href and not href.startswith("http"):
                # Build full URL from base
                base = self.BASE_URL.split('.com')[0] + '.com'
                job_url = f"{base}{href}"
            else:
                job_url = href or ""

            # Extract job ID from URL
            job_id = ""
            if "/job/" in job_url:
                job_id = job_url.split("/job/")[-1].split("/")[0].split("?")[0]

            # Get location
            location_el = await card.query_selector('[data-automation-id="locations"], dd[class*="css-"], span[class*="location"]')
            location = await location_el.text_content() if location_el else ""

            # Get posted date if available
            posted_el = await card.query_selector('[data-automation-id="postedOn"], time')
            posted_text = await posted_el.text_content() if posted_el else ""
            posted_date = None
            if posted_text:
                try:
                    posted_date = datetime.strptime(posted_text.strip(), "%Y-%m-%d")
                except:
                    pass

            if title:
                return ScrapedJob(
                    title=title.strip(),
                    location=location.strip() if location else "",
                    job_url=job_url,
                    external_job_id=job_id,
                    posted_date=posted_date,
                )
        except Exception as e:
            self.logger.debug(f"Error parsing job card: {e}")
        return None

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """Not used for Playwright scraper."""
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
    """Factory function to create Workday scraper classes using Playwright."""
    base_url = f"https://{tenant}.{subdomain}.myworkdayjobs.com/{job_site_path}"

    class WorkdayScraper(WorkdayPlaywrightMixin, PlaywrightScraper):
        config = ScraperConfig(
            company_slug=slug,
            company_name=name,
            careers_url=base_url,
            scraper_type=ScraperType.PLAYWRIGHT,
            rate_limit=10,
            max_pages=10,
            page_timeout=45,
        )
        BASE_URL = base_url

    WorkdayScraper.__name__ = f"{slug.title().replace(' ', '')}Scraper"
    WorkdayScraper.__qualname__ = WorkdayScraper.__name__
    return WorkdayScraper


# Register all Workday scrapers
for company_config in WORKDAY_COMPANIES:
    slug, name, tenant, subdomain, job_site_path = company_config
    scraper_class = create_workday_scraper(slug, name, tenant, subdomain, job_site_path)
    ScraperRegistry.register(category="enterprise")(scraper_class)
