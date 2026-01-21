"""
Base applicant class for auto-apply functionality.

Provides common functionality for all ATS applicants.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
import asyncio
import logging
import os

logger = logging.getLogger(__name__)


@dataclass
class ApplicantProfile:
    """User profile data for job applications."""
    # Personal info
    first_name: str
    last_name: str
    email: str
    phone: str

    # Address
    address_line1: Optional[str] = None
    address_line2: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    postal_code: Optional[str] = None
    country: Optional[str] = None

    # Work authorization
    us_authorized: Optional[str] = None  # "yes" or "no"
    requires_sponsorship: Optional[str] = None  # "yes" or "no"

    # Social profiles
    linkedin_url: Optional[str] = None
    github_url: Optional[str] = None
    portfolio_url: Optional[str] = None

    # Professional
    years_of_experience: Optional[int] = None
    current_company: Optional[str] = None
    current_title: Optional[str] = None

    # Demographics (EEO)
    gender: Optional[str] = None
    ethnicity: Optional[str] = None
    veteran_status: Optional[str] = None
    disability_status: Optional[str] = None

    # Custom answers (question pattern -> answer)
    custom_answers: Dict[str, str] = field(default_factory=dict)


@dataclass
class ApplyResult:
    """Result of an application submission attempt."""
    success: bool
    job_id: int
    user_id: int

    # ATS details
    ats_type: str
    application_url: str

    # Results
    confirmation_id: Optional[str] = None
    screenshot_path: Optional[str] = None

    # Errors
    error_message: Optional[str] = None
    error_step: Optional[str] = None  # Which step failed

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0

    # Debug info
    debug_info: Dict[str, Any] = field(default_factory=dict)


class BaseApplicant(ABC):
    """
    Abstract base class for ATS application submission.

    Provides common functionality:
    - Browser page management via browser pool
    - Screenshot capture
    - Error handling
    - Form filling utilities
    """

    ATS_TYPE: str = "unknown"

    def __init__(self, browser_pool=None):
        """
        Initialize the applicant.

        Args:
            browser_pool: Browser pool for Playwright pages
        """
        self.browser_pool = browser_pool
        self.logger = logging.getLogger(f"auto_apply.{self.ATS_TYPE}")
        self._page = None

    async def submit_application(
        self,
        job_id: int,
        user_id: int,
        application_url: str,
        profile: ApplicantProfile,
        resume_path: str,
        cover_letter_text: Optional[str] = None,
    ) -> ApplyResult:
        """
        Submit a job application.

        Args:
            job_id: Database job ID
            user_id: Database user ID
            application_url: URL to the job application page
            profile: Applicant profile data
            resume_path: Path to resume file
            cover_letter_text: Optional cover letter text

        Returns:
            ApplyResult with success/failure and details
        """
        started_at = datetime.utcnow()

        try:
            self.logger.info(f"Starting application submission for job {job_id}")

            # Get a browser page
            self._page = await self._get_page()

            # Navigate to application page
            await self._navigate_to_application(application_url)

            # Fill the application form
            await self._fill_application(profile, resume_path, cover_letter_text)

            # Submit the application
            confirmation_id = await self._submit_form()

            # Take confirmation screenshot
            screenshot_path = await self._take_screenshot("confirmation")

            completed_at = datetime.utcnow()

            self.logger.info(f"Application submitted successfully for job {job_id}")

            return ApplyResult(
                success=True,
                job_id=job_id,
                user_id=user_id,
                ats_type=self.ATS_TYPE,
                application_url=application_url,
                confirmation_id=confirmation_id,
                screenshot_path=screenshot_path,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=(completed_at - started_at).total_seconds(),
            )

        except Exception as e:
            completed_at = datetime.utcnow()

            # Try to take error screenshot
            screenshot_path = None
            try:
                screenshot_path = await self._take_screenshot("error")
            except Exception:
                pass

            self.logger.error(f"Application failed for job {job_id}: {str(e)}")

            return ApplyResult(
                success=False,
                job_id=job_id,
                user_id=user_id,
                ats_type=self.ATS_TYPE,
                application_url=application_url,
                error_message=str(e),
                screenshot_path=screenshot_path,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=(completed_at - started_at).total_seconds(),
            )

        finally:
            # Release the page back to pool
            await self._release_page()

    async def _get_page(self):
        """Get a browser page from the pool."""
        if not self.browser_pool:
            raise RuntimeError(
                "BaseApplicant requires a browser_pool. "
                "Pass browser_pool to the constructor."
            )
        return await self.browser_pool.acquire()

    async def _release_page(self):
        """Release the page back to the pool."""
        if self._page and self.browser_pool:
            await self.browser_pool.release(self._page)
            self._page = None

    async def _take_screenshot(self, name: str) -> Optional[str]:
        """Take a screenshot and return the path."""
        if not self._page:
            return None

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            screenshots_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                "data", "screenshots"
            )
            os.makedirs(screenshots_dir, exist_ok=True)

            path = os.path.join(
                screenshots_dir,
                f"apply_{self.ATS_TYPE}_{name}_{timestamp}.png"
            )
            await self._page.screenshot(path=path)
            self.logger.info(f"Screenshot saved: {path}")
            return path
        except Exception as e:
            self.logger.debug(f"Could not take screenshot: {e}")
            return None

    @abstractmethod
    async def _navigate_to_application(self, application_url: str):
        """Navigate to the application page and wait for it to load."""
        pass

    @abstractmethod
    async def _fill_application(
        self,
        profile: ApplicantProfile,
        resume_path: str,
        cover_letter_text: Optional[str],
    ):
        """Fill in the application form."""
        pass

    @abstractmethod
    async def _submit_form(self) -> Optional[str]:
        """Submit the application and return confirmation ID if available."""
        pass

    # Utility methods for form filling

    async def _fill_input(self, selector: str, value: str, clear_first: bool = True):
        """Fill an input field."""
        if not self._page or not value:
            return

        try:
            await self._page.wait_for_selector(selector, timeout=5000)
            if clear_first:
                await self._page.fill(selector, "")
            await self._page.fill(selector, value)
        except Exception as e:
            self.logger.debug(f"Could not fill {selector}: {e}")

    async def _click(self, selector: str, wait_after: float = 0.5):
        """Click an element."""
        if not self._page:
            return

        try:
            await self._page.wait_for_selector(selector, timeout=5000)
            await self._page.click(selector)
            if wait_after > 0:
                await asyncio.sleep(wait_after)
        except Exception as e:
            self.logger.debug(f"Could not click {selector}: {e}")

    async def _select_option(self, selector: str, value: str):
        """Select an option from a dropdown."""
        if not self._page or not value:
            return

        try:
            await self._page.wait_for_selector(selector, timeout=5000)
            await self._page.select_option(selector, value=value)
        except Exception as e:
            self.logger.debug(f"Could not select {value} in {selector}: {e}")

    async def _upload_file(self, selector: str, file_path: str):
        """Upload a file to a file input."""
        if not self._page or not file_path:
            return

        try:
            await self._page.wait_for_selector(selector, timeout=5000)
            await self._page.set_input_files(selector, file_path)
        except Exception as e:
            self.logger.debug(f"Could not upload file to {selector}: {e}")

    async def _check_checkbox(self, selector: str, checked: bool = True):
        """Check or uncheck a checkbox."""
        if not self._page:
            return

        try:
            await self._page.wait_for_selector(selector, timeout=5000)
            if checked:
                await self._page.check(selector)
            else:
                await self._page.uncheck(selector)
        except Exception as e:
            self.logger.debug(f"Could not set checkbox {selector}: {e}")

    async def _wait_for_navigation(self, timeout: int = 30000):
        """Wait for page navigation to complete."""
        if not self._page:
            return

        try:
            await self._page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception as e:
            self.logger.debug(f"Navigation wait timed out: {e}")

    async def _get_text(self, selector: str) -> Optional[str]:
        """Get text content from an element."""
        if not self._page:
            return None

        try:
            element = await self._page.query_selector(selector)
            if element:
                return await element.text_content()
        except Exception:
            pass
        return None

    async def _element_exists(self, selector: str) -> bool:
        """Check if an element exists on the page."""
        if not self._page:
            return False

        try:
            element = await self._page.query_selector(selector)
            return element is not None
        except Exception:
            return False
