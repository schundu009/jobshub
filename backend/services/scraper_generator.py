"""Dynamic scraper generator service.

This service automatically detects the job board type from a careers URL
and generates appropriate scraper code for new companies.
"""

import re
import os
import asyncio
import aiohttp
import ssl
from typing import Optional, Tuple, Dict, Any
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)


class JobBoardDetector:
    """Detects job board platform from URL patterns."""

    PATTERNS = {
        'workday': [
            r'\.wd\d+\.myworkdayjobs\.com',
            r'workday\.com',
        ],
        'greenhouse': [
            r'boards\.greenhouse\.io',
            r'boards-api\.greenhouse\.io',
            r'job-boards\.greenhouse\.io',
        ],
        'lever': [
            r'jobs\.lever\.co',
            r'api\.lever\.co',
        ],
        'ashby': [
            r'jobs\.ashbyhq\.com',
            r'api\.ashbyhq\.com',
        ],
        'eightfold': [
            r'\.eightfold\.ai',
            r'apply\.careers\.microsoft\.com',
            r'jobs\.careers\.microsoft\.com',
        ],
        'icims': [
            r'careers-.*\.icims\.com',
            r'\.icims\.com',
        ],
        'smartrecruiters': [
            r'careers\.smartrecruiters\.com',
            r'jobs\.smartrecruiters\.com',
        ],
        'bamboohr': [
            r'.*\.bamboohr\.com/careers',
            r'.*\.bamboohr\.com/jobs',
        ],
    }

    @classmethod
    def detect(cls, url: str) -> Tuple[str, Dict[str, str]]:
        """Detect job board type from URL."""
        for board_type, patterns in cls.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url, re.IGNORECASE):
                    metadata = cls._extract_metadata(url, board_type)
                    return board_type, metadata
        return 'unknown', {}

    @classmethod
    def _extract_metadata(cls, url: str, board_type: str) -> Dict[str, str]:
        """Extract metadata like company slug from URL based on board type."""
        metadata = {}
        parsed = urlparse(url)

        if board_type == 'workday':
            match = re.match(r'([^.]+)\.wd\d+\.myworkdayjobs\.com', parsed.netloc)
            if match:
                metadata['workday_company'] = match.group(1)
                path_parts = parsed.path.strip('/').split('/')
                if path_parts and path_parts[-1]:
                    metadata['workday_board'] = path_parts[-1]

        elif board_type == 'greenhouse':
            match = re.search(r'/boards?/([^/]+)', parsed.path)
            if match:
                metadata['greenhouse_board'] = match.group(1)

        elif board_type == 'lever':
            match = re.search(r'lever\.co/([^/]+)', url)
            if match:
                metadata['lever_company'] = match.group(1)

        elif board_type == 'ashby':
            match = re.search(r'ashbyhq\.com/(?:posting-api/job-board/)?([^/]+)', url)
            if match:
                metadata['ashby_company'] = match.group(1)

        elif board_type == 'eightfold':
            # URL format: {company}.eightfold.ai/careers?domain={domain}
            # Or custom domain: apply.careers.microsoft.com/careers?domain={domain}
            from urllib.parse import parse_qs
            query_params = parse_qs(parsed.query)

            # Check for standard Eightfold subdomain
            match = re.match(r'([^.]+)\.eightfold\.ai', parsed.netloc)
            if match:
                metadata['eightfold_subdomain'] = match.group(1)
            else:
                # Custom domain - use full hostname
                metadata['eightfold_subdomain'] = parsed.netloc

            # Extract domain from query string
            if 'domain' in query_params:
                metadata['eightfold_domain'] = query_params['domain'][0]
            elif 'microsoft' in parsed.netloc:
                metadata['eightfold_domain'] = 'microsoft.com'

        return metadata


class ScraperGenerator:
    """Generates scraper code for new companies."""

    def __init__(self):
        self.scrapers_dir = os.path.dirname(os.path.dirname(__file__)) + '/scrapers'
        self.custom_dir = os.path.join(self.scrapers_dir, 'custom')
        os.makedirs(self.custom_dir, exist_ok=True)

        init_file = os.path.join(self.custom_dir, '__init__.py')
        if not os.path.exists(init_file):
            with open(init_file, 'w') as f:
                f.write('"""Custom auto-generated scrapers."""\n')

    def _slugify(self, name: str) -> str:
        """Convert company name to slug."""
        slug = name.lower()
        slug = re.sub(r'[^a-z0-9]+', '', slug)
        return slug

    def _to_class_name(self, name: str) -> str:
        """Convert company name to valid Python class name."""
        words = re.split(r'[^a-zA-Z0-9]+', name)
        return ''.join(word.capitalize() for word in words if word)

    async def detect_and_validate(self, careers_url: str) -> Tuple[str, Dict[str, Any]]:
        """Detect job board type and validate the API endpoint works."""
        board_type, metadata = JobBoardDetector.detect(careers_url)

        if board_type == 'unknown':
            board_type, metadata = await self._probe_api(careers_url)

        if board_type == 'unknown':
            return 'unknown', {'error': 'Could not detect job board type'}

        api_info = await self._validate_api(board_type, metadata, careers_url)
        return board_type, api_info

    async def _probe_api(self, careers_url: str) -> Tuple[str, Dict[str, str]]:
        """Try to detect job board by probing the careers page."""
        ssl_context = ssl.create_default_context()
        try:
            import certifi
            ssl_context.load_verify_locations(certifi.where())
        except ImportError:
            pass
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                async with session.get(careers_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    if resp.status == 200:
                        text = await resp.text()

                        gh_match = re.search(r'boards\.greenhouse\.io/([^/"\']+)', text)
                        if gh_match:
                            return 'greenhouse', {'greenhouse_board': gh_match.group(1)}

                        lever_match = re.search(r'jobs\.lever\.co/([^/"\']+)', text)
                        if lever_match:
                            return 'lever', {'lever_company': lever_match.group(1)}

                        ashby_match = re.search(r'jobs\.ashbyhq\.com/([^/"\']+)', text)
                        if ashby_match:
                            return 'ashby', {'ashby_company': ashby_match.group(1)}

                        wd_match = re.search(r'([^/"\']+)\.wd\d+\.myworkdayjobs\.com[^"\']*?/([^/"\']+)', text)
                        if wd_match:
                            return 'workday', {
                                'workday_company': wd_match.group(1),
                                'workday_board': wd_match.group(2)
                            }
            except Exception as e:
                logger.warning(f"Error probing {careers_url}: {e}")

        return 'unknown', {}

    async def _validate_api(self, board_type: str, metadata: Dict, careers_url: str) -> Dict[str, Any]:
        """Validate the API endpoint and return API info."""
        ssl_context = ssl.create_default_context()
        try:
            import certifi
            ssl_context.load_verify_locations(certifi.where())
        except ImportError:
            pass
        connector = aiohttp.TCPConnector(ssl=ssl_context)

        api_url = None
        job_count = 0

        async with aiohttp.ClientSession(connector=connector) as session:
            try:
                if board_type == 'workday':
                    company = metadata.get('workday_company', '')
                    board = metadata.get('workday_board', 'External')
                    for wd_num in ['wd1', 'wd5', 'wd3']:
                        test_url = f"https://{company}.{wd_num}.myworkdayjobs.com/wday/cxs/{company}/{board}/jobs"
                        try:
                            async with session.post(
                                test_url,
                                json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""},
                                timeout=aiohttp.ClientTimeout(total=15)
                            ) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    if 'total' in data:
                                        api_url = test_url
                                        job_count = data.get('total', 0)
                                        metadata['workday_num'] = wd_num
                                        break
                        except:
                            continue

                elif board_type == 'greenhouse':
                    board_id = metadata.get('greenhouse_board', '')
                    api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs"
                    async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            job_count = len(data.get('jobs', []))

                elif board_type == 'lever':
                    company = metadata.get('lever_company', '')
                    api_url = f"https://api.lever.co/v0/postings/{company}"
                    async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            job_count = len(data) if isinstance(data, list) else 0

                elif board_type == 'ashby':
                    company = metadata.get('ashby_company', '')
                    api_url = f"https://api.ashbyhq.com/posting-api/job-board/{company}"
                    async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            job_count = len(data.get('jobs', []))

                elif board_type == 'eightfold':
                    subdomain = metadata.get('eightfold_subdomain', '')
                    domain = metadata.get('eightfold_domain', f'{subdomain}.com')
                    # Determine base URL - standard Eightfold or custom domain
                    if '.' in subdomain and 'eightfold' not in subdomain:
                        # Custom domain like apply.careers.microsoft.com
                        base_url = f"https://{subdomain}"
                    else:
                        base_url = f"https://{subdomain}.eightfold.ai"
                    # Eightfold uses a public sitemap - count jobs from there
                    api_url = f"{base_url}/careers/sitemap.xml?domain={domain}"
                    async with session.get(api_url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            # Count job URLs in sitemap
                            job_count = len(re.findall(r'/careers/job/\d+', text))

            except Exception as e:
                logger.error(f"Error validating API: {e}")
                return {'error': str(e), 'metadata': metadata}

        return {
            'api_url': api_url,
            'job_count': job_count,
            'metadata': metadata,
            'valid': api_url is not None and job_count > 0
        }

    def generate_scraper(
        self,
        company_name: str,
        careers_url: str,
        board_type: str,
        api_info: Dict[str, Any]
    ) -> Tuple[str, str]:
        """Generate scraper code and save to file."""
        slug = self._slugify(company_name)
        class_name = self._to_class_name(company_name)
        metadata = api_info.get('metadata', {})

        if board_type == 'workday':
            code = self._generate_workday_scraper(
                company_name, slug, class_name, careers_url, api_info, metadata
            )
        elif board_type == 'greenhouse':
            code = self._generate_greenhouse_scraper(
                company_name, slug, class_name, careers_url, metadata
            )
        elif board_type == 'lever':
            code = self._generate_lever_scraper(
                company_name, slug, class_name, careers_url, metadata
            )
        elif board_type == 'ashby':
            code = self._generate_ashby_scraper(
                company_name, slug, class_name, careers_url, metadata
            )
        elif board_type == 'eightfold':
            code = self._generate_eightfold_scraper(
                company_name, slug, class_name, careers_url, metadata
            )
        else:
            raise ValueError(f"Unsupported board type: {board_type}")

        file_path = os.path.join(self.custom_dir, f"{slug}.py")
        with open(file_path, 'w') as f:
            f.write(code)

        return slug, file_path

    def _generate_greenhouse_scraper(self, company_name, slug, class_name, careers_url, metadata):
        board_id = metadata.get('greenhouse_board', slug)
        return f'''"""{ company_name} job scraper - auto-generated Greenhouse scraper."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="custom")
class {class_name}Scraper(HTTPScraper):
    """Auto-generated scraper for {company_name} careers (Greenhouse)."""

    config = ScraperConfig(
        company_slug="{slug}",
        company_name="{company_name}",
        careers_url="{careers_url}",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []

        params = {{"content": "true"}}
        data = await self.fetch_json(self.API_URL, params=params)

        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data returned")

        jobs = data.get("jobs", [])
        for job in jobs:
            parsed = self.parse_job(job)
            if parsed:
                all_jobs.append(parsed)

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            jobs_found=len(all_jobs),
            error_message=None
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            job_id = str(raw.get("id", ""))

            location_data = raw.get("location", {{}})
            location = location_data.get("name", "") if isinstance(location_data, dict) else str(location_data)

            updated_at = raw.get("updated_at", "")
            posted_date = None
            if updated_at:
                try:
                    posted_date = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                except:
                    pass

            job_url = raw.get("absolute_url", f"https://boards.greenhouse.io/{board_id}/jobs/{{job_id}}")
            description = raw.get("content", "")

            departments = raw.get("departments", [])
            department = departments[0].get("name", "") if departments else ""

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=job_id,
                job_description=description,
                department=department,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {{e}}")
            return None
'''

    def _generate_lever_scraper(self, company_name, slug, class_name, careers_url, metadata):
        lever_company = metadata.get('lever_company', slug)
        return f'''"""{company_name} job scraper - auto-generated Lever scraper."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="custom")
class {class_name}Scraper(HTTPScraper):
    """Auto-generated scraper for {company_name} careers (Lever)."""

    config = ScraperConfig(
        company_slug="{slug}",
        company_name="{company_name}",
        careers_url="{careers_url}",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.lever.co/v0/postings/{lever_company}"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []

        data = await self.fetch_json(self.API_URL)

        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data returned")

        if isinstance(data, list):
            for job in data:
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            jobs_found=len(all_jobs),
            error_message=None
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("text", "")
            job_id = raw.get("id", "")

            categories = raw.get("categories", {{}})
            location = categories.get("location", "")
            department = categories.get("team", "")

            created_at = raw.get("createdAt", 0)
            posted_date = None
            if created_at:
                try:
                    posted_date = datetime.fromtimestamp(created_at / 1000)
                except:
                    pass

            job_url = raw.get("hostedUrl", f"https://jobs.lever.co/{lever_company}/{{job_id}}")
            description = raw.get("descriptionPlain", "")

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=job_id,
                job_description=description,
                department=department,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {{e}}")
            return None
'''

    def _generate_ashby_scraper(self, company_name, slug, class_name, careers_url, metadata):
        ashby_company = metadata.get('ashby_company', slug)
        return f'''"""{company_name} job scraper - auto-generated Ashby scraper."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="custom")
class {class_name}Scraper(HTTPScraper):
    """Auto-generated scraper for {company_name} careers (Ashby)."""

    config = ScraperConfig(
        company_slug="{slug}",
        company_name="{company_name}",
        careers_url="{careers_url}",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=10,
    )

    API_URL = "https://api.ashbyhq.com/posting-api/job-board/{ashby_company}"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []

        data = await self.fetch_json(self.API_URL)

        if not data:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No data returned")

        jobs = data.get("jobs", [])
        for job in jobs:
            parsed = self.parse_job(job)
            if parsed:
                all_jobs.append(parsed)

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            jobs_found=len(all_jobs),
            error_message=None
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            job_id = raw.get("id", "")

            location = raw.get("location", "")
            if isinstance(location, dict):
                location = location.get("name", "")

            published_at = raw.get("publishedAt", "")
            posted_date = None
            if published_at:
                try:
                    posted_date = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
                except:
                    pass

            job_url = raw.get("jobUrl", f"https://jobs.ashbyhq.com/{ashby_company}/{{job_id}}")
            department = raw.get("department", "")
            if isinstance(department, dict):
                department = department.get("name", "")

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=job_id,
                job_description=raw.get("descriptionHtml", ""),
                department=department,
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {{e}}")
            return None
'''

    def _generate_eightfold_scraper(self, company_name, slug, class_name, careers_url, metadata):
        subdomain = metadata.get('eightfold_subdomain', slug)
        domain = metadata.get('eightfold_domain', f'{subdomain}.com')

        # Determine base URL - standard Eightfold or custom domain
        if '.' in subdomain and 'eightfold' not in subdomain:
            # Custom domain like apply.careers.microsoft.com
            base_url = f"https://{subdomain}"
        else:
            base_url = f"https://{subdomain}.eightfold.ai"

        return f'''"""{company_name} job scraper - auto-generated Eightfold scraper."""

import re
from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime
from urllib.parse import unquote


@ScraperRegistry.register(category="custom")
class {class_name}Scraper(HTTPScraper):
    """Auto-generated scraper for {company_name} careers (Eightfold)."""

    config = ScraperConfig(
        company_slug="{slug}",
        company_name="{company_name}",
        careers_url="{careers_url}",
        scraper_type=ScraperType.HTTP,
        rate_limit=10,
        max_pages=100,
    )

    BASE_URL = "{base_url}"
    DOMAIN = "{domain}"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []

        # Eightfold provides a public sitemap with all job URLs
        sitemap_url = f"{{self.BASE_URL}}/careers/sitemap.xml?domain={{self.DOMAIN}}"

        try:
            sitemap_text = await self.fetch_text(sitemap_url)
            if not sitemap_text:
                return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="No sitemap data")

            # Parse job URLs from sitemap
            job_urls = re.findall(r'<loc>(https?://[^<]+/careers/job/\\d+[^<]*)</loc>', sitemap_text)

            for job_url in job_urls:
                parsed = self.parse_job_from_url(job_url)
                if parsed:
                    all_jobs.append(parsed)

            return ScrapeResult(
                success=True,
                jobs=all_jobs,
                jobs_found=len(all_jobs),
                error_message=None
            )
        except Exception as e:
            self.logger.error(f"Error scraping Eightfold: {{e}}")
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message=str(e))

    def parse_job_from_url(self, job_url: str) -> Optional[ScrapedJob]:
        """Parse job info from Eightfold URL structure."""
        try:
            # URL format: .../careers/job/ID/Title-Slug?location=Location&...
            match = re.search(r'/careers/job/(\\d+)/([^?]+)', job_url)
            if not match:
                return None

            job_id = match.group(1)
            slug = match.group(2)

            # Decode URL-encoded slug
            slug = unquote(slug)

            # Extract title from slug (convert dashes/underscores to spaces, clean up)
            title = slug.replace('-', ' ').replace('_', ' ')
            # Remove common suffixes and clean up
            title = re.sub(r'\\s+\\d+$', '', title)  # Remove trailing numbers
            title = ' '.join(title.split())  # Normalize whitespace
            title = title.title()  # Title case

            # Extract location from query string if present
            location = None
            if 'location=' in job_url:
                loc_match = re.search(r'location=([^&]+)', job_url)
                if loc_match:
                    location = unquote(loc_match.group(1))

            # Truncate fields to avoid database errors
            title = title[:255] if title else "Unknown Position"
            location = location[:255] if location else None
            truncated_url = job_url[:500] if len(job_url) > 500 else job_url

            return ScrapedJob(
                title=title,
                location=location,
                job_url=truncated_url,
                external_job_id=job_id,
                job_description="",
                department="",
                posted_date=None,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job URL {{job_url}}: {{e}}")
            return None

    async def fetch_text(self, url: str) -> Optional[str]:
        """Fetch URL and return text content."""
        import aiohttp
        import ssl

        ssl_context = ssl.create_default_context()
        try:
            import certifi
            ssl_context.load_verify_locations(certifi.where())
        except ImportError:
            pass

        connector = aiohttp.TCPConnector(ssl=ssl_context)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                if resp.status == 200:
                    return await resp.text()
        return None
'''

    def _generate_workday_scraper(self, company_name, slug, class_name, careers_url, api_info, metadata):
        api_url = api_info.get('api_url', '')
        company = metadata.get('workday_company', slug)
        board = metadata.get('workday_board', 'External')
        wd_num = metadata.get('workday_num', 'wd1')
        job_url_base = f"https://{company}.{wd_num}.myworkdayjobs.com/en-US/{board}"

        return f'''"""{company_name} job scraper - auto-generated Workday scraper."""

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, ScrapedJob, ScrapeResult
from scrapers.registry import ScraperRegistry
from typing import List, Optional
from datetime import datetime


@ScraperRegistry.register(category="custom")
class {class_name}Scraper(HTTPScraper):
    """Auto-generated scraper for {company_name} careers (Workday)."""

    config = ScraperConfig(
        company_slug="{slug}",
        company_name="{company_name}",
        careers_url="{careers_url}",
        scraper_type=ScraperType.HTTP,
        rate_limit=20,
        max_pages=50,
    )

    API_URL = "{api_url}"

    async def scrape(self) -> ScrapeResult:
        all_jobs: List[ScrapedJob] = []
        offset = 0
        limit = 20

        while offset < self.config.max_pages * limit:
            payload = {{
                "appliedFacets": {{}},
                "limit": limit,
                "offset": offset,
                "searchText": ""
            }}

            data = await self.fetch_json(self.API_URL, method="POST", payload=payload)
            if not data:
                break

            job_postings = data.get("jobPostings", [])
            if not job_postings:
                break

            for job in job_postings:
                parsed = self.parse_job(job)
                if parsed:
                    all_jobs.append(parsed)

            total = data.get("total", 0)
            offset += limit
            if offset >= total:
                break

        return ScrapeResult(
            success=True,
            jobs=all_jobs,
            jobs_found=len(all_jobs),
            error_message=None
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = raw.get("title", "")
            external_id = raw.get("bulletFields", [""])[0] if raw.get("bulletFields") else ""
            location = raw.get("locationsText", "")
            posted_on = raw.get("postedOn", "")

            posted_date = None
            if posted_on:
                try:
                    posted_date = datetime.strptime(posted_on, "%Y-%m-%dT%H:%M:%S.%f%z")
                except:
                    try:
                        posted_date = datetime.strptime(posted_on.split("T")[0], "%Y-%m-%d")
                    except:
                        pass

            job_path = raw.get("externalPath", "")
            job_url = f"{job_url_base}{{job_path}}"

            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url,
                external_job_id=external_id or job_path,
                job_description="",
                department="",
                posted_date=posted_date,
            )
        except Exception as e:
            self.logger.error(f"Error parsing job: {{e}}")
            return None
'''

    def reload_scrapers(self):
        """Reload scraper registry to pick up new scrapers."""
        from scrapers.registry import ScraperRegistry
        import importlib
        import sys

        for key in list(sys.modules.keys()):
            if key.startswith('scrapers.custom'):
                del sys.modules[key]

        try:
            import scrapers.custom
            importlib.reload(scrapers.custom)
        except ImportError:
            pass

        for filename in os.listdir(self.custom_dir):
            if filename.endswith('.py') and filename != '__init__.py':
                module_name = f"scrapers.custom.{filename[:-3]}"
                try:
                    if module_name in sys.modules:
                        importlib.reload(sys.modules[module_name])
                    else:
                        importlib.import_module(module_name)
                except Exception as e:
                    logger.error(f"Error loading {module_name}: {e}")


scraper_generator = ScraperGenerator()
