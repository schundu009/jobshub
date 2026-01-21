"""
Workday ATS Auto-Apply Handler.

Handles authentication and form submission for Workday career sites.
Workday is more complex than Greenhouse/Lever as it requires:
1. Account creation or login
2. Multi-step application forms
3. Company-specific configurations
"""

import asyncio
import logging
import re
from typing import Optional
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from .base import BaseApplicant, ApplicantProfile, ApplyResult

logger = logging.getLogger(__name__)


class WorkdayApplicant(BaseApplicant):
    """
    Handles job applications on Workday ATS.

    Workday URLs typically look like:
    - https://{company}.wd5.myworkdayjobs.com/en-US/{career-site}/job/{job-title}/{job-id}
    - https://company.wd1.myworkdayjobs.com/External/job/Location/Title_JR123456
    """

    # Common Workday selectors
    SELECTORS = {
        # Login/Sign In
        "sign_in_link": "[data-automation-id='signInLink'], a[href*='login'], button:has-text('Sign In')",
        "create_account_link": "[data-automation-id='createAccountLink'], a:has-text('Create Account')",
        "email_input": "[data-automation-id='email'], input[type='email'], #input-4",
        "password_input": "[data-automation-id='password'], input[type='password'], #input-5",
        "sign_in_button": "[data-automation-id='signInSubmitButton'], button[type='submit']:has-text('Sign In')",

        # Create Account
        "create_email": "[data-automation-id='createAccountEmail'], input[name='email']",
        "create_password": "[data-automation-id='createAccountPassword'], input[name='password']",
        "verify_password": "[data-automation-id='verifyPassword'], input[name='verifyPassword']",
        "create_account_button": "[data-automation-id='createAccountSubmitButton'], button:has-text('Create Account')",
        "agree_checkbox": "[data-automation-id='agreementCheckbox'], input[type='checkbox']",

        # Apply button
        "apply_button": "[data-automation-id='applyButton'], button:has-text('Apply'), a:has-text('Apply')",
        "apply_manually_button": "button:has-text('Apply Manually'), [data-automation-id='applyManually']",

        # Personal Information
        "first_name": "[data-automation-id='legalNameSection_firstName'], input[name='firstName']",
        "last_name": "[data-automation-id='legalNameSection_lastName'], input[name='lastName']",
        "preferred_name": "[data-automation-id='preferredName'], input[name='preferredName']",
        "address_line1": "[data-automation-id='addressSection_addressLine1'], input[name='addressLine1']",
        "address_line2": "[data-automation-id='addressSection_addressLine2'], input[name='addressLine2']",
        "city": "[data-automation-id='addressSection_city'], input[name='city']",
        "state": "[data-automation-id='addressSection_countryRegion'], select[name='state']",
        "postal_code": "[data-automation-id='addressSection_postalCode'], input[name='postalCode']",
        "country": "[data-automation-id='addressSection_country'], select[name='country']",
        "phone": "[data-automation-id='phone-number'], input[type='tel'], input[name='phone']",
        "phone_device_type": "[data-automation-id='phone-device-type']",

        # Resume/Documents
        "resume_upload": "[data-automation-id='file-upload-input-ref'], input[type='file']",
        "resume_section": "[data-automation-id='resumeSection']",
        "select_file_button": "button:has-text('Select Files'), [data-automation-id='selectFilesButton']",

        # Work Experience
        "add_experience_button": "[data-automation-id='Add Work Experience']",
        "job_title_input": "[data-automation-id='jobTitle']",
        "company_input": "[data-automation-id='company']",
        "start_date": "[data-automation-id='startDate']",
        "end_date": "[data-automation-id='endDate']",
        "currently_working": "[data-automation-id='currentlyWorkHere']",

        # Education
        "add_education_button": "[data-automation-id='Add Education']",
        "school_input": "[data-automation-id='school']",
        "degree_input": "[data-automation-id='degree']",
        "field_of_study": "[data-automation-id='fieldOfStudy']",

        # Social/Links
        "linkedin_input": "[data-automation-id='linkedInProfile'], input[name='linkedin']",
        "website_input": "[data-automation-id='website'], input[name='website']",

        # EEO/Compliance
        "gender_dropdown": "[data-automation-id='gender']",
        "ethnicity_dropdown": "[data-automation-id='ethnicityDropdown'], [data-automation-id='ethnicity']",
        "veteran_dropdown": "[data-automation-id='veteranStatus']",
        "disability_dropdown": "[data-automation-id='disabilityStatus']",

        # Work Authorization
        "work_auth_question": "[data-automation-id='workAuthorization']",
        "sponsorship_question": "[data-automation-id='sponsorship']",

        # Navigation
        "next_button": "[data-automation-id='bottom-navigation-next-button'], button:has-text('Next'), button:has-text('Continue')",
        "previous_button": "[data-automation-id='bottom-navigation-previous-button'], button:has-text('Previous'), button:has-text('Back')",
        "submit_button": "[data-automation-id='bottom-navigation-next-button']:has-text('Submit'), button:has-text('Submit Application')",
        "save_button": "[data-automation-id='saveForLaterButton'], button:has-text('Save')",

        # Confirmation
        "confirmation_message": "[data-automation-id='confirmationMessage'], .congratulations, .success-message",
        "application_id": "[data-automation-id='applicationId']",

        # Error handling
        "error_message": "[data-automation-id='errorMessage'], .error-message, .validation-error",
    }

    def __init__(self, browser_pool, workday_email: Optional[str] = None, workday_password: Optional[str] = None):
        super().__init__(browser_pool)
        self.workday_email = workday_email
        self.workday_password = workday_password

    async def submit_application(
        self,
        job_id: int,
        user_id: int,
        application_url: str,
        profile: ApplicantProfile,
        resume_path: str,
        cover_letter_text: Optional[str] = None,
    ) -> ApplyResult:
        """Submit application to Workday."""
        page = None

        try:
            page = await self.browser_pool.get_page()

            # Navigate to job page
            logger.info(f"Navigating to Workday job: {application_url}")
            await page.goto(application_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)

            # Click Apply button
            apply_clicked = await self._click_apply_button(page)
            if not apply_clicked:
                return ApplyResult(
                    success=False,
                    job_id=job_id,
                    user_id=user_id,
                    ats_type="workday",
                    application_url=application_url,
                    error_message="Could not find Apply button",
                )

            await asyncio.sleep(2)

            # Handle login/create account if needed
            if await self._is_login_required(page):
                login_success = await self._handle_authentication(page, profile)
                if not login_success:
                    screenshot_path = await self._take_screenshot(page, job_id, "login_failed")
                    return ApplyResult(
                        success=False,
                        job_id=job_id,
                        user_id=user_id,
                        ats_type="workday",
                        application_url=application_url,
                        error_message="Failed to authenticate with Workday",
                        screenshot_path=screenshot_path,
                    )

            # Fill application form (multi-step)
            form_success = await self._fill_application_form(page, profile, resume_path, cover_letter_text)
            if not form_success:
                screenshot_path = await self._take_screenshot(page, job_id, "form_error")
                return ApplyResult(
                    success=False,
                    job_id=job_id,
                    user_id=user_id,
                    ats_type="workday",
                    application_url=application_url,
                    error_message="Failed to complete application form",
                    screenshot_path=screenshot_path,
                )

            # Submit and get confirmation
            confirmation_id = await self._submit_and_confirm(page, job_id)
            screenshot_path = await self._take_screenshot(page, job_id, "confirmation")

            if confirmation_id:
                return ApplyResult(
                    success=True,
                    job_id=job_id,
                    user_id=user_id,
                    ats_type="workday",
                    application_url=application_url,
                    confirmation_id=confirmation_id,
                    screenshot_path=screenshot_path,
                )
            else:
                return ApplyResult(
                    success=False,
                    job_id=job_id,
                    user_id=user_id,
                    ats_type="workday",
                    application_url=application_url,
                    error_message="Could not confirm submission",
                    screenshot_path=screenshot_path,
                )

        except PlaywrightTimeout as e:
            logger.error(f"Timeout during Workday application: {e}")
            screenshot_path = await self._take_screenshot(page, job_id, "timeout") if page else None
            return ApplyResult(
                success=False,
                job_id=job_id,
                user_id=user_id,
                ats_type="workday",
                application_url=application_url,
                error_message=f"Timeout: {str(e)}",
                screenshot_path=screenshot_path,
            )
        except Exception as e:
            logger.exception(f"Error during Workday application: {e}")
            screenshot_path = await self._take_screenshot(page, job_id, "error") if page else None
            return ApplyResult(
                success=False,
                job_id=job_id,
                user_id=user_id,
                ats_type="workday",
                application_url=application_url,
                error_message=str(e),
                screenshot_path=screenshot_path,
            )
        finally:
            if page:
                await self.browser_pool.release_page(page)

    async def _click_apply_button(self, page: Page) -> bool:
        """Find and click the Apply button."""
        try:
            # Try multiple selectors
            for selector in [
                self.SELECTORS["apply_button"],
                "button:has-text('Apply')",
                "a:has-text('Apply')",
                "[data-automation-id='applyButton']",
            ]:
                try:
                    button = page.locator(selector).first
                    if await button.is_visible(timeout=3000):
                        await button.click()
                        logger.info("Clicked Apply button")
                        return True
                except:
                    continue

            # Try Apply Manually if main apply not found
            try:
                manual_button = page.locator(self.SELECTORS["apply_manually_button"]).first
                if await manual_button.is_visible(timeout=2000):
                    await manual_button.click()
                    logger.info("Clicked Apply Manually button")
                    return True
            except:
                pass

            return False
        except Exception as e:
            logger.error(f"Error clicking apply button: {e}")
            return False

    async def _is_login_required(self, page: Page) -> bool:
        """Check if login/sign-in is required."""
        try:
            # Check for sign-in elements
            sign_in = page.locator(self.SELECTORS["sign_in_link"])
            create_account = page.locator(self.SELECTORS["create_account_link"])
            email_input = page.locator(self.SELECTORS["email_input"])

            for element in [sign_in, create_account, email_input]:
                try:
                    if await element.is_visible(timeout=2000):
                        return True
                except:
                    continue

            return False
        except:
            return False

    async def _handle_authentication(self, page: Page, profile: ApplicantProfile) -> bool:
        """Handle Workday login or account creation."""
        try:
            # Use stored credentials or profile email
            email = self.workday_email or profile.email
            password = self.workday_password

            # Check if we need to sign in or create account
            sign_in_visible = False
            create_account_visible = False

            try:
                sign_in_visible = await page.locator(self.SELECTORS["sign_in_link"]).is_visible(timeout=2000)
            except:
                pass

            try:
                create_account_visible = await page.locator(self.SELECTORS["create_account_link"]).is_visible(timeout=2000)
            except:
                pass

            if sign_in_visible and password:
                # Try to sign in with existing account
                logger.info("Attempting to sign in to Workday")
                return await self._sign_in(page, email, password)
            elif create_account_visible:
                # Create new account
                logger.info("Creating new Workday account")
                return await self._create_account(page, email, password or self._generate_temp_password())
            else:
                # Maybe already on application form or email-only sign in
                email_input = page.locator(self.SELECTORS["email_input"]).first
                if await email_input.is_visible(timeout=2000):
                    await email_input.fill(email)

                    # Look for continue/next button
                    continue_btn = page.locator("button:has-text('Continue'), button:has-text('Next')").first
                    if await continue_btn.is_visible(timeout=2000):
                        await continue_btn.click()
                        await asyncio.sleep(2)

                        # Check if password is required
                        password_input = page.locator(self.SELECTORS["password_input"]).first
                        if await password_input.is_visible(timeout=2000) and password:
                            await password_input.fill(password)
                            await page.locator(self.SELECTORS["sign_in_button"]).click()
                            await asyncio.sleep(2)

                    return True

            return False

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

    async def _sign_in(self, page: Page, email: str, password: str) -> bool:
        """Sign in to existing Workday account."""
        try:
            # Click sign in link if visible
            try:
                sign_in_link = page.locator(self.SELECTORS["sign_in_link"]).first
                if await sign_in_link.is_visible(timeout=2000):
                    await sign_in_link.click()
                    await asyncio.sleep(1)
            except:
                pass

            # Fill email
            email_input = page.locator(self.SELECTORS["email_input"]).first
            await email_input.fill(email)

            # Fill password
            password_input = page.locator(self.SELECTORS["password_input"]).first
            await password_input.fill(password)

            # Click sign in
            sign_in_btn = page.locator(self.SELECTORS["sign_in_button"]).first
            await sign_in_btn.click()

            await asyncio.sleep(3)

            # Check for errors
            try:
                error = page.locator(self.SELECTORS["error_message"]).first
                if await error.is_visible(timeout=2000):
                    error_text = await error.text_content()
                    logger.error(f"Sign in error: {error_text}")
                    return False
            except:
                pass

            return True

        except Exception as e:
            logger.error(f"Sign in error: {e}")
            return False

    async def _create_account(self, page: Page, email: str, password: str) -> bool:
        """Create new Workday account."""
        try:
            # Click create account link
            try:
                create_link = page.locator(self.SELECTORS["create_account_link"]).first
                if await create_link.is_visible(timeout=2000):
                    await create_link.click()
                    await asyncio.sleep(1)
            except:
                pass

            # Fill email
            email_input = page.locator(self.SELECTORS["create_email"]).first
            if not await email_input.is_visible(timeout=2000):
                email_input = page.locator(self.SELECTORS["email_input"]).first
            await email_input.fill(email)

            # Fill password
            password_input = page.locator(self.SELECTORS["create_password"]).first
            if not await password_input.is_visible(timeout=2000):
                password_input = page.locator(self.SELECTORS["password_input"]).first
            await password_input.fill(password)

            # Verify password if field exists
            try:
                verify_input = page.locator(self.SELECTORS["verify_password"]).first
                if await verify_input.is_visible(timeout=1000):
                    await verify_input.fill(password)
            except:
                pass

            # Check agreement checkbox if exists
            try:
                checkbox = page.locator(self.SELECTORS["agree_checkbox"]).first
                if await checkbox.is_visible(timeout=1000):
                    await checkbox.check()
            except:
                pass

            # Click create account
            create_btn = page.locator(self.SELECTORS["create_account_button"]).first
            if not await create_btn.is_visible(timeout=2000):
                create_btn = page.locator("button:has-text('Create'), button[type='submit']").first
            await create_btn.click()

            await asyncio.sleep(3)

            return True

        except Exception as e:
            logger.error(f"Create account error: {e}")
            return False

    def _generate_temp_password(self) -> str:
        """Generate a temporary password for account creation."""
        import secrets
        import string
        alphabet = string.ascii_letters + string.digits + "!@#$%"
        return ''.join(secrets.choice(alphabet) for _ in range(16))

    async def _fill_application_form(
        self,
        page: Page,
        profile: ApplicantProfile,
        resume_path: str,
        cover_letter_text: Optional[str]
    ) -> bool:
        """Fill the multi-step Workday application form."""
        try:
            max_steps = 10  # Safety limit
            step = 0

            while step < max_steps:
                step += 1
                logger.info(f"Processing application step {step}")

                # Try to fill any visible fields
                await self._fill_visible_fields(page, profile)

                # Try to upload resume if on resume section
                await self._try_upload_resume(page, resume_path)

                # Look for Next/Continue button
                next_btn = page.locator(self.SELECTORS["next_button"]).first
                submit_btn = page.locator(self.SELECTORS["submit_button"]).first

                # If Submit button is visible, we're on the last step
                try:
                    if await submit_btn.is_visible(timeout=2000):
                        logger.info("Reached submit step")
                        return True
                except:
                    pass

                # Click Next if visible
                try:
                    if await next_btn.is_visible(timeout=2000):
                        await next_btn.click()
                        await asyncio.sleep(2)
                        continue
                except:
                    pass

                # No more navigation buttons found
                break

            return True

        except Exception as e:
            logger.error(f"Error filling form: {e}")
            return False

    async def _fill_visible_fields(self, page: Page, profile: ApplicantProfile):
        """Fill all visible form fields."""
        # Personal info
        await self._fill_input(page, self.SELECTORS["first_name"], profile.first_name)
        await self._fill_input(page, self.SELECTORS["last_name"], profile.last_name)
        await self._fill_input(page, self.SELECTORS["phone"], profile.phone)

        # Address
        if profile.address_line1:
            await self._fill_input(page, self.SELECTORS["address_line1"], profile.address_line1)
        if profile.address_line2:
            await self._fill_input(page, self.SELECTORS["address_line2"], profile.address_line2)
        if profile.city:
            await self._fill_input(page, self.SELECTORS["city"], profile.city)
        if profile.postal_code:
            await self._fill_input(page, self.SELECTORS["postal_code"], profile.postal_code)

        # State/Country dropdowns
        if profile.state:
            await self._select_option(page, self.SELECTORS["state"], profile.state)
        if profile.country:
            await self._select_option(page, self.SELECTORS["country"], profile.country)

        # LinkedIn
        if profile.linkedin_url:
            await self._fill_input(page, self.SELECTORS["linkedin_input"], profile.linkedin_url)

        # EEO fields (optional)
        if profile.gender:
            await self._select_option(page, self.SELECTORS["gender_dropdown"], profile.gender)
        if profile.ethnicity:
            await self._select_option(page, self.SELECTORS["ethnicity_dropdown"], profile.ethnicity)
        if profile.veteran_status:
            await self._select_option(page, self.SELECTORS["veteran_dropdown"], profile.veteran_status)
        if profile.disability_status:
            await self._select_option(page, self.SELECTORS["disability_dropdown"], profile.disability_status)

        # Work authorization
        await self._handle_work_auth_questions(page, profile)

    async def _try_upload_resume(self, page: Page, resume_path: str):
        """Try to upload resume if upload field is visible."""
        try:
            # Look for file upload input
            file_input = page.locator(self.SELECTORS["resume_upload"]).first

            if await file_input.is_visible(timeout=2000):
                await file_input.set_input_files(resume_path)
                logger.info("Uploaded resume")
                await asyncio.sleep(2)
                return

            # Try clicking Select Files button first
            select_btn = page.locator(self.SELECTORS["select_file_button"]).first
            if await select_btn.is_visible(timeout=2000):
                # This might open a file dialog - handle with file chooser
                async with page.expect_file_chooser() as fc_info:
                    await select_btn.click()
                file_chooser = await fc_info.value
                await file_chooser.set_files(resume_path)
                logger.info("Uploaded resume via file chooser")
                await asyncio.sleep(2)

        except Exception as e:
            logger.debug(f"Resume upload not available or error: {e}")

    async def _handle_work_auth_questions(self, page: Page, profile: ApplicantProfile):
        """Handle work authorization questions."""
        try:
            # US Work Authorization
            work_auth = page.locator(self.SELECTORS["work_auth_question"]).first
            if await work_auth.is_visible(timeout=1000):
                value = "Yes" if profile.us_authorized else "No"
                await self._select_option(page, self.SELECTORS["work_auth_question"], value)

            # Sponsorship
            sponsorship = page.locator(self.SELECTORS["sponsorship_question"]).first
            if await sponsorship.is_visible(timeout=1000):
                value = "Yes" if profile.requires_sponsorship else "No"
                await self._select_option(page, self.SELECTORS["sponsorship_question"], value)

        except Exception as e:
            logger.debug(f"Work auth questions not found or error: {e}")

    async def _submit_and_confirm(self, page: Page, job_id: int) -> Optional[str]:
        """Submit application and extract confirmation ID."""
        try:
            # Click submit button
            submit_btn = page.locator(self.SELECTORS["submit_button"]).first
            if not await submit_btn.is_visible(timeout=3000):
                submit_btn = page.locator("button:has-text('Submit')").first

            await submit_btn.click()
            logger.info("Clicked submit button")

            await asyncio.sleep(5)

            # Look for confirmation
            confirmation = page.locator(self.SELECTORS["confirmation_message"]).first
            if await confirmation.is_visible(timeout=10000):
                logger.info("Found confirmation message")

                # Try to extract application ID
                try:
                    app_id_elem = page.locator(self.SELECTORS["application_id"]).first
                    if await app_id_elem.is_visible(timeout=2000):
                        return await app_id_elem.text_content()
                except:
                    pass

                # Try to find ID in page content
                content = await page.content()
                id_match = re.search(r'application.*?(\d{6,})', content, re.IGNORECASE)
                if id_match:
                    return id_match.group(1)

                return f"WD-{job_id}-confirmed"

            return None

        except Exception as e:
            logger.error(f"Submit error: {e}")
            return None
