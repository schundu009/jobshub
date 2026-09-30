"""
Base scraper classes for the custom job scraper system.

Provides:
- ScraperConfig: Configuration dataclass for scrapers
- ScrapedJob: Normalized job data structure
- ScrapeResult: Result of a scraping operation
- BaseScraper: Abstract base class with common functionality
- HTTPScraper: For sites with JSON APIs
- PlaywrightScraper: For JavaScript-heavy sites
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import asyncio
import logging
import hashlib
import re

import ssl
import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class ScraperType(Enum):
    """Type of scraper based on the technology needed."""
    HTTP = "http"          # JSON APIs, simple HTML
    PLAYWRIGHT = "playwright"  # JavaScript-heavy sites


class ScraperErrorType(Enum):
    """Categorized error types for monitoring."""
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    BLOCKED = "blocked"
    PARSE_ERROR = "parse_error"
    NETWORK_ERROR = "network_error"
    AUTH_ERROR = "auth_error"
    EMPTY_RESULT = "empty_result"  # 0 jobs from a board that previously had jobs
    UNEXPECTED_RESPONSE = "unexpected_response"  # wrong JSON shape / every posting unparseable
    SAVE_FAILED = "save_failed"  # jobs were found but none reached the database
    UNKNOWN = "unknown"


class UnexpectedResponseError(Exception):
    """The API answered, but not with the shape the scraper expects."""


@dataclass
class ScraperConfig:
    """Configuration for a company scraper."""
    company_slug: str
    company_name: str
    careers_url: str
    scraper_type: ScraperType

    # Rate limiting
    rate_limit: int = 30  # requests per minute

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 2.0  # seconds between retries

    # Timeouts
    page_timeout: int = 30  # seconds
    request_timeout: int = 15  # seconds for individual requests

    # Pagination
    max_pages: int = 100  # safety limit
    page_size: int = 50  # jobs per page if configurable

    # Optional API endpoints
    api_url: Optional[str] = None

    # Custom headers
    headers: dict = field(default_factory=dict)

    # Disabled scrapers are kept in the codebase but not registered, so the
    # orchestrator, admin status page and manual-run endpoints never see them.
    # Always give a reason, e.g. "board dead as of 2026-09-29; new ATS unknown".
    enabled: bool = True
    disabled_reason: Optional[str] = None

    # Set True for boards that legitimately go to zero openings; otherwise a
    # 0-job scrape of a board that has produced jobs before is reported as a
    # failure (ScraperErrorType.EMPTY_RESULT) instead of a silent success.
    allow_empty: bool = False


@dataclass
class ScrapedJob:
    """Normalized job data from any career portal."""
    title: str
    location: str
    job_url: str
    external_job_id: str

    # Optional fields
    job_description: Optional[str] = None
    department: Optional[str] = None
    posted_date: Optional[datetime] = None
    salary_min: Optional[int] = None
    salary_max: Optional[int] = None
    employment_type: Optional[str] = None  # full-time, part-time, contract
    remote_type: Optional[str] = None  # remote, hybrid, on-site

    # Structured work terms when the ATS/board provides them (contracts.classifier
    # prefers these over text parsing). employment_type_raw is the board's own
    # label ("Contract", "FullTime", "Contract to Hire", ...).
    employment_type_raw: Optional[str] = None
    pay_rate_min: Optional[float] = None
    pay_rate_max: Optional[float] = None
    pay_period: Optional[str] = None  # hour | day | week | month | year
    extra: dict = field(default_factory=dict)  # e.g. agency_name, end_client, skills, tax_terms text

    # Metadata
    scraped_at: datetime = field(default_factory=datetime.utcnow)
    raw_data: Optional[dict] = None  # Original data for debugging

    def to_dict(self) -> dict:
        """Convert to dictionary for database insertion."""
        return {
            "title": self.title,
            "location": self.location,
            "job_url": self.job_url,
            "external_job_id": self.external_job_id,
            "job_description": self.job_description,
            "department": self.department,
            "posted_date": self.posted_date,
            "salary_min": self.salary_min,
            "salary_max": self.salary_max,
        }

    def generate_id(self) -> str:
        """Generate a unique ID if external_job_id is not available."""
        content = f"{self.title}|{self.location}|{self.job_url}"
        return hashlib.md5(content.encode()).hexdigest()[:16]


@dataclass
class ScrapeResult:
    """Result of a scraping operation."""
    success: bool
    jobs: list[ScrapedJob] = field(default_factory=list)
    jobs_found: int = 0
    jobs_new: int = 0
    jobs_updated: int = 0

    # Timing
    duration_seconds: float = 0.0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Errors
    error_message: Optional[str] = None
    error_type: Optional[ScraperErrorType] = None

    # Pagination info
    pages_scraped: int = 0
    total_pages: Optional[int] = None

    # Set by the caller after save_scraped_jobs (SaveResult.as_dict(), or
    # {"exception": "..."} when saving raised). None = saving wasn't attempted.
    save_stats: Optional[dict] = None

    def __post_init__(self):
        if self.jobs:
            self.jobs_found = len(self.jobs)


class BaseScraper(ABC):
    """
    Abstract base class for all company scrapers.

    Provides common functionality:
    - Retry logic with exponential backoff
    - Error categorization
    - Logging
    - Rate limiting integration
    """

    config: ScraperConfig

    def __init__(self, rate_limiter=None, browser_pool=None):
        """
        Initialize the scraper.

        Args:
            rate_limiter: Optional rate limiter instance
            browser_pool: Optional browser pool for Playwright scrapers
        """
        self.rate_limiter = rate_limiter
        self.browser_pool = browser_pool
        self.logger = logging.getLogger(f"scraper.{self.config.company_slug}")
        # A runner may set this directly; otherwise resolve_api_url() looks in
        # ScraperConfigDB.config_overrides["url_override"] (written by auto-heal).
        self.url_override: Optional[str] = None

    def resolve_api_url(self, default: Optional[str] = None) -> Optional[str]:
        """
        Return the API URL to scrape.

        Precedence: self.url_override (set by a runner) > DB
        config_overrides["url_override"] > class API_URL / default.
        DB lookup failures (no DB configured, table missing) fall back silently.
        """
        if self.url_override:
            return self.url_override
        default = default or getattr(self, "API_URL", None) or self.config.api_url
        try:
            from database import SessionLocal
            from models import ScraperConfigDB

            with SessionLocal() as db:
                cfg = db.query(ScraperConfigDB).filter_by(
                    company_slug=self.config.company_slug
                ).first()
                override = (cfg.config_overrides or {}).get("url_override") if cfg else None
                if override:
                    self.logger.info(f"Using url_override for {self.config.company_slug}: {override}")
                    self.url_override = override
                    return override
        except Exception as e:
            self.logger.debug(f"url_override lookup skipped: {e}")
        return default

    def expect_list(self, data: Any, key: Optional[str] = None) -> list:
        """
        Return data[key] (or data itself when key is None) if it is a list,
        else raise UnexpectedResponseError. Use in scrape() to catch APIs that
        changed shape or started returning an HTML/error payload.
        """
        value = data.get(key) if (key and isinstance(data, dict)) else (None if key else data)
        if not isinstance(value, list):
            got = type(data).__name__
            if isinstance(data, dict):
                got += f" keys={sorted(data)[:8]}"
            raise UnexpectedResponseError(
                f"expected list{f' at {key!r}' if key else ''}, got {got}"
            )
        return value

    def parse_all(self, raw_jobs: list) -> list["ScrapedJob"]:
        """
        Parse raw postings with parse_job(). If the API returned postings but
        none could be parsed, raise UnexpectedResponseError rather than
        reporting a successful 0-job scrape.
        """
        parsed = [job for job in (self.parse_job(raw) for raw in raw_jobs) if job]
        if raw_jobs and not parsed:
            raise UnexpectedResponseError(
                f"parse_job rejected all {len(raw_jobs)} postings"
            )
        return parsed

    def previously_had_jobs(self) -> bool:
        """
        True if ScraperConfigDB says this scraper has found jobs before.
        If the DB can't be read, assume True so empty results are surfaced.
        """
        try:
            from database import SessionLocal
            from models import ScraperConfigDB

            with SessionLocal() as db:
                cfg = db.query(ScraperConfigDB).filter_by(
                    company_slug=self.config.company_slug
                ).first()
                return bool(cfg and (cfg.total_jobs_found or 0) > 0)
        except Exception as e:
            self.logger.debug(f"job-history lookup failed: {e}")
            return True

    def _check_empty(self, result: "ScrapeResult") -> "ScrapeResult":
        """Turn a 'successful' 0-job scrape into a failure when that's suspicious."""
        if (
            result.success
            and not result.jobs
            and not self.config.allow_empty
            and self.previously_had_jobs()
        ):
            result.success = False
            result.error_type = ScraperErrorType.EMPTY_RESULT
            result.error_message = (
                result.error_message
                or f"0 jobs returned for {self.config.company_name}, which has had "
                "jobs before - board moved, API changed, or all postings filtered out"
            )
        return result

    async def run(self) -> ScrapeResult:
        """
        Entry point with retry logic and error handling.

        Returns:
            ScrapeResult with success/failure and job data
        """
        started_at = datetime.utcnow()
        last_error = None
        last_error_type = ScraperErrorType.UNKNOWN

        try:
            for attempt in range(1, self.config.max_retries + 1):
                try:
                    self.logger.info(
                        f"Starting scrape attempt {attempt}/{self.config.max_retries} "
                        f"for {self.config.company_name}"
                    )

                    # Wait for rate limiter if configured
                    if self.rate_limiter:
                        await self.rate_limiter.acquire(self.config.company_slug)

                    # Run the actual scraper
                    result = await self.scrape()
                    result.started_at = started_at
                    result.completed_at = datetime.utcnow()
                    result.duration_seconds = (
                        result.completed_at - started_at
                    ).total_seconds()

                    self.logger.info(
                        f"Scrape completed for {self.config.company_name}: "
                        f"{result.jobs_found} jobs found in {result.duration_seconds:.1f}s"
                    )

                    return self._check_empty(result)

                except UnexpectedResponseError as e:
                    last_error = f"Unexpected response: {e}"
                    last_error_type = ScraperErrorType.UNEXPECTED_RESPONSE
                    self.logger.warning(f"Unexpected response on attempt {attempt}: {e}")

                except asyncio.TimeoutError as e:
                    last_error = str(e) or "Request timed out"
                    last_error_type = ScraperErrorType.TIMEOUT
                    self.logger.warning(f"Timeout on attempt {attempt}: {last_error}")

                except aiohttp.ClientResponseError as e:
                    if e.status == 429:
                        last_error = f"Rate limited: {e.message}"
                        last_error_type = ScraperErrorType.RATE_LIMITED
                    elif e.status == 403:
                        last_error = f"Access forbidden: {e.message}"
                        last_error_type = ScraperErrorType.BLOCKED
                    elif e.status == 401:
                        last_error = f"Authentication required: {e.message}"
                        last_error_type = ScraperErrorType.AUTH_ERROR
                    else:
                        last_error = f"HTTP {e.status}: {e.message}"
                        last_error_type = ScraperErrorType.NETWORK_ERROR
                    self.logger.warning(f"HTTP error on attempt {attempt}: {last_error}")

                except aiohttp.ClientError as e:
                    last_error = f"Network error: {str(e)}"
                    last_error_type = ScraperErrorType.NETWORK_ERROR
                    self.logger.warning(f"Network error on attempt {attempt}: {last_error}")

                except (ValueError, KeyError, TypeError) as e:
                    last_error = f"Parse error: {str(e)}"
                    last_error_type = ScraperErrorType.PARSE_ERROR
                    self.logger.warning(f"Parse error on attempt {attempt}: {last_error}")

                except Exception as e:
                    last_error = f"Unexpected error: {str(e)}"
                    last_error_type = ScraperErrorType.UNKNOWN
                    self.logger.exception(f"Unexpected error on attempt {attempt}")

                # Wait before retry with exponential backoff
                if attempt < self.config.max_retries:
                    delay = self.config.retry_delay * (2 ** (attempt - 1))
                    self.logger.info(f"Waiting {delay}s before retry...")
                    await asyncio.sleep(delay)

            # All retries exhausted
            completed_at = datetime.utcnow()
            self.logger.error(
                f"Scrape failed for {self.config.company_name} after "
                f"{self.config.max_retries} attempts: {last_error}"
            )

            return ScrapeResult(
                success=False,
                error_message=last_error,
                error_type=last_error_type,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=(completed_at - started_at).total_seconds(),
            )
        finally:
            # Always cleanup resources
            await self.cleanup()

    @abstractmethod
    async def scrape(self) -> ScrapeResult:
        """
        Implement the actual scraping logic.

        Must be implemented by each company scraper.

        Returns:
            ScrapeResult with jobs and metadata
        """
        pass

    async def cleanup(self):
        """
        Cleanup resources after scraping.

        Override in subclasses if needed.
        """
        pass

    @abstractmethod
    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        """
        Parse raw job data into a normalized ScrapedJob.

        Must be implemented by each company scraper.

        Args:
            raw: Raw job data from the API/page

        Returns:
            ScrapedJob or None if parsing fails
        """
        pass

    def clean_text(self, text: Optional[str]) -> Optional[str]:
        """Clean and normalize text content."""
        if not text:
            return None
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text if text else None

    def clean_html(self, html: Optional[str]) -> Optional[str]:
        """Convert HTML to plain text."""
        if not html:
            return None
        soup = BeautifulSoup(html, 'html.parser')
        # Remove script and style elements
        for element in soup(['script', 'style']):
            element.decompose()
        text = soup.get_text(separator=' ')
        return self.clean_text(text)

    def parse_date(self, date_str: Optional[str]) -> Optional[datetime]:
        """Parse various date formats into datetime."""
        if not date_str:
            return None

        # Common formats
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%d/%m/%Y",
            "%B %d, %Y",
            "%b %d, %Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        self.logger.debug(f"Could not parse date: {date_str}")
        return None

    def parse_salary(self, salary_str: Optional[str]) -> tuple[Optional[int], Optional[int]]:
        """Parse salary string into min/max integers."""
        if not salary_str:
            return None, None

        # Find all numbers in the string
        numbers = re.findall(r'[\d,]+', salary_str)
        if not numbers:
            return None, None

        # Convert to integers
        values = []
        for num in numbers:
            try:
                value = int(num.replace(',', ''))
                # Handle abbreviated values like 100K
                if value < 1000 and 'k' in salary_str.lower():
                    value *= 1000
                values.append(value)
            except ValueError:
                continue

        if len(values) == 1:
            return values[0], values[0]
        elif len(values) >= 2:
            return min(values), max(values)

        return None, None


class HTTPScraper(BaseScraper):
    """
    Base class for scrapers using HTTP requests (JSON APIs).

    Provides:
    - Async HTTP client management
    - JSON fetching with retry
    - Common headers
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._session: Optional[aiohttp.ClientSession] = None

    async def get_session(self) -> aiohttp.ClientSession:
        """Get or create an aiohttp session."""
        if self._session is None or self._session.closed:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "application/json, text/html, */*",
                "Accept-Language": "en-US,en;q=0.9",
            }
            headers.update(self.config.headers)

            timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)

            # Create SSL context with proper certificate verification
            ssl_context = ssl.create_default_context()
            # Use certifi for better CA bundle if available
            try:
                import certifi
                ssl_context.load_verify_locations(certifi.where())
            except ImportError:
                pass  # Use system CA bundle

            connector = aiohttp.TCPConnector(ssl=ssl_context)
            self._session = aiohttp.ClientSession(
                headers=headers,
                timeout=timeout,
                connector=connector,
            )

        return self._session

    async def close(self):
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    async def cleanup(self):
        """Cleanup HTTP session after scraping."""
        await self.close()

    async def fetch_json(
        self,
        url: str,
        method: str = "GET",
        params: Optional[dict] = None,
        json_data: Optional[dict] = None,
        headers: Optional[dict] = None,
        payload: Optional[dict] = None,  # Backward compatibility alias for json_data
        json: Optional[dict] = None,  # Alias used by some scrapers (aiohttp-style)
    ) -> dict:
        """
        Fetch JSON data from a URL.

        Args:
            url: URL to fetch
            method: HTTP method (GET, POST)
            params: Query parameters
            json_data: JSON body for POST requests
            headers: Additional headers
            payload: Alias for json_data (backward compatibility)

        Returns:
            Parsed JSON response
        """
        # Support 'payload' as alias for 'json_data'
        if payload is not None and json_data is None:
            json_data = payload
        if json is not None and json_data is None:
            json_data = json

        session = await self.get_session()

        request_headers = {}
        if headers:
            request_headers.update(headers)

        async with session.request(
            method,
            url,
            params=params,
            json=json_data,
            headers=request_headers,
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def fetch_html(
        self,
        url: str,
        params: Optional[dict] = None,
    ) -> str:
        """
        Fetch HTML content from a URL.

        Args:
            url: URL to fetch
            params: Query parameters

        Returns:
            HTML content as string
        """
        session = await self.get_session()

        async with session.get(url, params=params) as response:
            response.raise_for_status()
            return await response.text()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


class PlaywrightScraper(BaseScraper):
    """
    Base class for scrapers using Playwright (JavaScript-heavy sites).

    Provides:
    - Browser page management via browser pool
    - Wait for element utilities
    - Screenshot on error
    - Infinite scroll handling
    """

    async def get_page(self):
        """
        Get a browser page from the pool.

        Returns:
            Playwright Page object
        """
        if not self.browser_pool:
            raise RuntimeError(
                "PlaywrightScraper requires a browser_pool. "
                "Pass browser_pool to the constructor."
            )
        return await self.browser_pool.acquire()

    async def release_page(self, page):
        """Release a page back to the pool."""
        if self.browser_pool:
            await self.browser_pool.release(page)

    async def wait_for_jobs(self, page, selector: str, timeout: int = None):
        """
        Wait for job elements to appear on the page.

        Args:
            page: Playwright Page object
            selector: CSS selector for job elements
            timeout: Timeout in milliseconds
        """
        timeout = timeout or self.config.page_timeout * 1000
        await page.wait_for_selector(selector, timeout=timeout)

    async def scroll_to_bottom(
        self,
        page,
        pause: float = 1.0,
        max_scrolls: int = 50,
    ):
        """
        Scroll to the bottom of the page for infinite scroll sites.

        Args:
            page: Playwright Page object
            pause: Pause between scrolls in seconds
            max_scrolls: Maximum number of scrolls
        """
        for _ in range(max_scrolls):
            previous_height = await page.evaluate("document.body.scrollHeight")
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await asyncio.sleep(pause)
            current_height = await page.evaluate("document.body.scrollHeight")

            if current_height == previous_height:
                break

    async def extract_text(self, page, selector: str) -> Optional[str]:
        """Extract text content from an element."""
        try:
            element = await page.query_selector(selector)
            if element:
                return await element.text_content()
        except Exception as e:
            self.logger.debug(f"Could not extract text from {selector}: {e}")
        return None

    async def extract_attribute(
        self,
        page,
        selector: str,
        attribute: str,
    ) -> Optional[str]:
        """Extract an attribute from an element."""
        try:
            element = await page.query_selector(selector)
            if element:
                return await element.get_attribute(attribute)
        except Exception as e:
            self.logger.debug(f"Could not extract {attribute} from {selector}: {e}")
        return None

    async def take_debug_screenshot(self, page, name: str):
        """Take a screenshot for debugging."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = f"/tmp/scraper_debug_{self.config.company_slug}_{name}_{timestamp}.png"
            await page.screenshot(path=path)
            self.logger.info(f"Debug screenshot saved: {path}")
        except Exception as e:
            self.logger.debug(f"Could not take screenshot: {e}")
