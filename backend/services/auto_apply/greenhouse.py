"""
Greenhouse ATS application submission handler.

Greenhouse applications typically have:
- Personal info (name, email, phone)
- Resume upload
- Cover letter (text or file)
- Custom questions
- EEO questions (optional)
"""

import asyncio
from typing import Optional
from .base import BaseApplicant, ApplicantProfile


class GreenhouseApplicant(BaseApplicant):
    """
    Applicant handler for Greenhouse ATS.

    Greenhouse forms are typically at:
    - https://boards.greenhouse.io/{company}/jobs/{job_id}
    - Click "Apply" to get to application form
    """

    ATS_TYPE = "greenhouse"

    # Common selectors for Greenhouse forms
    SELECTORS = {
        # Personal info
        "first_name": "#first_name, input[name='first_name'], input[autocomplete='given-name']",
        "last_name": "#last_name, input[name='last_name'], input[autocomplete='family-name']",
        "email": "#email, input[name='email'], input[type='email']",
        "phone": "#phone, input[name='phone'], input[type='tel']",

        # Resume
        "resume_input": "input[type='file'][name*='resume'], input[type='file'][data-field='resume']",
        "resume_dropzone": ".resume-upload, .file-upload, [data-field='resume']",

        # Cover letter
        "cover_letter_text": "textarea[name*='cover_letter'], textarea[data-field='cover_letter']",
        "cover_letter_input": "input[type='file'][name*='cover_letter']",

        # Location
        "location": "#location, input[name='location'], input[placeholder*='location']",

        # LinkedIn
        "linkedin": "input[name*='linkedin'], input[placeholder*='LinkedIn']",

        # Work authorization
        "authorized_us": "select[name*='authorized'], select[name*='work_auth']",
        "sponsorship": "select[name*='sponsor'], select[name*='visa']",

        # Submit button
        "submit_button": "button[type='submit'], input[type='submit'], button:has-text('Submit'), button:has-text('Apply')",

        # Confirmation
        "confirmation": ".application-confirmation, .thank-you, h1:has-text('Thank'), h2:has-text('Thank')",

        # Apply button (on job page)
        "apply_button": "a:has-text('Apply'), button:has-text('Apply')",
    }

    async def _navigate_to_application(self, application_url: str):
        """Navigate to the Greenhouse application page."""
        self.logger.info(f"Navigating to {application_url}")

        await self._page.goto(application_url, wait_until="networkidle")
        await asyncio.sleep(1)

        # Check if we're on the job page and need to click Apply
        apply_button = await self._page.query_selector(self.SELECTORS["apply_button"])
        if apply_button:
            self.logger.info("Found Apply button, clicking...")
            await apply_button.click()
            await self._wait_for_navigation()
            await asyncio.sleep(1)

        # Wait for form to load
        await self._page.wait_for_selector(
            f"{self.SELECTORS['first_name']}, {self.SELECTORS['email']}",
            timeout=15000
        )

        self.logger.info("Application form loaded")

    async def _fill_application(
        self,
        profile: ApplicantProfile,
        resume_path: str,
        cover_letter_text: Optional[str],
    ):
        """Fill in the Greenhouse application form."""
        self.logger.info("Filling application form")

        # Personal info
        await self._fill_input(self.SELECTORS["first_name"], profile.first_name)
        await self._fill_input(self.SELECTORS["last_name"], profile.last_name)
        await self._fill_input(self.SELECTORS["email"], profile.email)
        await self._fill_input(self.SELECTORS["phone"], profile.phone)

        # Location
        if profile.city and profile.state:
            location = f"{profile.city}, {profile.state}"
            await self._fill_input(self.SELECTORS["location"], location)

        # LinkedIn
        if profile.linkedin_url:
            await self._fill_input(self.SELECTORS["linkedin"], profile.linkedin_url)

        # Resume upload
        await self._upload_resume(resume_path)

        # Cover letter
        if cover_letter_text:
            await self._fill_cover_letter(cover_letter_text)

        # Work authorization questions
        await self._fill_work_auth(profile)

        # EEO questions (optional)
        await self._fill_eeo(profile)

        # Custom questions
        await self._fill_custom_questions(profile)

        self.logger.info("Form filled successfully")

    async def _upload_resume(self, resume_path: str):
        """Upload resume file."""
        self.logger.info("Uploading resume")

        # Try file input first
        file_input = await self._page.query_selector(self.SELECTORS["resume_input"])
        if file_input:
            await file_input.set_input_files(resume_path)
            await asyncio.sleep(1)
            self.logger.info("Resume uploaded via file input")
            return

        # Try dropzone click to trigger file dialog
        dropzone = await self._page.query_selector(self.SELECTORS["resume_dropzone"])
        if dropzone:
            # Some dropzones have hidden file inputs
            file_inputs = await self._page.query_selector_all("input[type='file']")
            for file_input in file_inputs:
                try:
                    await file_input.set_input_files(resume_path)
                    await asyncio.sleep(1)
                    self.logger.info("Resume uploaded")
                    return
                except Exception:
                    continue

        self.logger.warning("Could not find resume upload field")

    async def _fill_cover_letter(self, cover_letter_text: str):
        """Fill cover letter textarea."""
        self.logger.info("Filling cover letter")

        textarea = await self._page.query_selector(self.SELECTORS["cover_letter_text"])
        if textarea:
            await textarea.fill(cover_letter_text)
            self.logger.info("Cover letter filled")
        else:
            self.logger.debug("No cover letter textarea found")

    async def _fill_work_auth(self, profile: ApplicantProfile):
        """Fill work authorization questions."""
        # US work authorization
        if profile.us_authorized:
            value = "Yes" if profile.us_authorized.lower() == "yes" else "No"
            selects = await self._page.query_selector_all("select")
            for select in selects:
                label = await self._get_select_label(select)
                if label and ("authorized" in label.lower() or "legally" in label.lower()):
                    try:
                        # Try to select by label text
                        options = await select.query_selector_all("option")
                        for opt in options:
                            opt_text = await opt.text_content()
                            if opt_text and value.lower() in opt_text.lower():
                                opt_value = await opt.get_attribute("value")
                                await select.select_option(value=opt_value)
                                break
                    except Exception as e:
                        self.logger.debug(f"Could not fill work auth: {e}")

        # Sponsorship
        if profile.requires_sponsorship:
            value = "Yes" if profile.requires_sponsorship.lower() == "yes" else "No"
            selects = await self._page.query_selector_all("select")
            for select in selects:
                label = await self._get_select_label(select)
                if label and ("sponsor" in label.lower() or "visa" in label.lower()):
                    try:
                        options = await select.query_selector_all("option")
                        for opt in options:
                            opt_text = await opt.text_content()
                            if opt_text and value.lower() in opt_text.lower():
                                opt_value = await opt.get_attribute("value")
                                await select.select_option(value=opt_value)
                                break
                    except Exception as e:
                        self.logger.debug(f"Could not fill sponsorship: {e}")

    async def _fill_eeo(self, profile: ApplicantProfile):
        """Fill EEO (Equal Employment Opportunity) questions if present."""
        # Gender
        if profile.gender:
            await self._select_eeo_option("gender", profile.gender)

        # Ethnicity
        if profile.ethnicity:
            await self._select_eeo_option("race", profile.ethnicity)
            await self._select_eeo_option("ethnic", profile.ethnicity)

        # Veteran status
        if profile.veteran_status:
            await self._select_eeo_option("veteran", profile.veteran_status)

        # Disability
        if profile.disability_status:
            await self._select_eeo_option("disability", profile.disability_status)

    async def _select_eeo_option(self, keyword: str, value: str):
        """Select an EEO option from a dropdown."""
        selects = await self._page.query_selector_all("select")
        for select in selects:
            select_id = await select.get_attribute("id") or ""
            select_name = await select.get_attribute("name") or ""

            if keyword in select_id.lower() or keyword in select_name.lower():
                try:
                    options = await select.query_selector_all("option")
                    for opt in options:
                        opt_text = (await opt.text_content() or "").lower()
                        opt_value = await opt.get_attribute("value") or ""

                        # Match common values
                        if self._matches_eeo_value(value, opt_text, opt_value):
                            await select.select_option(value=opt_value)
                            break
                except Exception as e:
                    self.logger.debug(f"Could not select EEO {keyword}: {e}")

    def _matches_eeo_value(self, profile_value: str, option_text: str, option_value: str) -> bool:
        """Check if an EEO option matches the profile value."""
        pv = profile_value.lower()

        # Gender mappings
        if pv in ["male", "man"]:
            return "male" in option_text or "man" in option_text
        if pv in ["female", "woman"]:
            return "female" in option_text or "woman" in option_text
        if pv in ["non_binary", "nonbinary", "non-binary"]:
            return "non" in option_text or "other" in option_text
        if pv == "decline":
            return "decline" in option_text or "prefer not" in option_text

        # Ethnicity mappings
        ethnicity_map = {
            "white": ["white", "caucasian"],
            "black": ["black", "african"],
            "asian": ["asian"],
            "hispanic": ["hispanic", "latino", "latina"],
            "american_indian": ["american indian", "native american", "alaska"],
            "pacific_islander": ["pacific", "hawaiian"],
            "two_or_more": ["two or more", "multiple", "mixed"],
        }
        for key, patterns in ethnicity_map.items():
            if key in pv:
                return any(p in option_text for p in patterns)

        # Veteran mappings
        if "veteran" in pv:
            return "veteran" in option_text and "not" not in option_text
        if "not_veteran" in pv or pv == "no":
            return "not" in option_text or "no" in option_text

        # Default: try exact match
        return pv in option_text or pv in option_value

    async def _get_select_label(self, select_element) -> Optional[str]:
        """Get the label text for a select element."""
        try:
            # Check for associated label
            select_id = await select_element.get_attribute("id")
            if select_id:
                label = await self._page.query_selector(f"label[for='{select_id}']")
                if label:
                    return await label.text_content()

            # Check parent for label
            parent = await select_element.evaluate_handle("el => el.parentElement")
            if parent:
                label = await parent.as_element().query_selector("label")
                if label:
                    return await label.text_content()
        except Exception:
            pass
        return None

    async def _fill_custom_questions(self, profile: ApplicantProfile):
        """Fill any custom questions using stored answers."""
        if not profile.custom_answers:
            return

        # Find all question containers
        questions = await self._page.query_selector_all(".field, .question, [data-question]")

        for question in questions:
            question_text = await question.text_content()
            if not question_text:
                continue

            question_text_lower = question_text.lower()

            # Check if we have an answer for this question
            for pattern, answer in profile.custom_answers.items():
                if pattern.lower() in question_text_lower:
                    # Try to fill the answer
                    input_field = await question.query_selector("input, textarea, select")
                    if input_field:
                        tag_name = await input_field.evaluate("el => el.tagName")
                        if tag_name == "SELECT":
                            await self._select_matching_option(input_field, answer)
                        else:
                            await input_field.fill(answer)
                        break

    async def _select_matching_option(self, select_element, answer: str):
        """Select the best matching option in a dropdown."""
        try:
            options = await select_element.query_selector_all("option")
            answer_lower = answer.lower()

            for opt in options:
                opt_text = (await opt.text_content() or "").lower()
                if answer_lower in opt_text or opt_text in answer_lower:
                    opt_value = await opt.get_attribute("value")
                    await select_element.select_option(value=opt_value)
                    return
        except Exception as e:
            self.logger.debug(f"Could not select option: {e}")

    async def _submit_form(self) -> Optional[str]:
        """Submit the application form and return confirmation ID."""
        self.logger.info("Submitting application")

        # Find and click submit button
        submit_button = await self._page.query_selector(self.SELECTORS["submit_button"])
        if not submit_button:
            raise Exception("Submit button not found")

        await submit_button.click()

        # Wait for confirmation page
        try:
            await self._page.wait_for_selector(
                self.SELECTORS["confirmation"],
                timeout=30000
            )
            self.logger.info("Confirmation page loaded")
        except Exception:
            # Check if there are validation errors
            error = await self._page.query_selector(".error, .validation-error, [role='alert']")
            if error:
                error_text = await error.text_content()
                raise Exception(f"Form validation error: {error_text}")
            raise Exception("Confirmation page not found after submit")

        # Try to extract confirmation ID from URL or page
        confirmation_id = await self._extract_confirmation_id()
        return confirmation_id

    async def _extract_confirmation_id(self) -> Optional[str]:
        """Extract confirmation ID from the confirmation page."""
        # Check URL for confirmation parameter
        url = self._page.url
        if "confirmation" in url or "thank" in url:
            import re
            match = re.search(r'[?&]id=([^&]+)', url)
            if match:
                return match.group(1)

        # Check page content for confirmation number
        page_text = await self._page.text_content("body")
        if page_text:
            import re
            # Look for patterns like "Confirmation: ABC123" or "Reference #: 12345"
            patterns = [
                r'confirmation[:\s#]*([A-Z0-9-]+)',
                r'reference[:\s#]*([A-Z0-9-]+)',
                r'application[:\s#]*([A-Z0-9-]+)',
            ]
            for pattern in patterns:
                match = re.search(pattern, page_text, re.IGNORECASE)
                if match:
                    return match.group(1)

        return None
