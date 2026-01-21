"""
Lever ATS application submission handler.

Lever applications are typically at:
- https://jobs.lever.co/{company}/{job_id}/apply
"""

import asyncio
from typing import Optional
from .base import BaseApplicant, ApplicantProfile


class LeverApplicant(BaseApplicant):
    """
    Applicant handler for Lever ATS.

    Lever forms have a specific structure:
    - Basic info (name, email, phone, location)
    - Resume upload
    - Optional cover letter
    - Links (LinkedIn, GitHub, etc.)
    - Custom questions
    """

    ATS_TYPE = "lever"

    # Common selectors for Lever forms
    SELECTORS = {
        # Personal info
        "name": "input[name='name'], #name",
        "email": "input[name='email'], #email",
        "phone": "input[name='phone'], #phone",
        "location": "input[name='location'], #location",
        "company": "input[name='org'], input[name='company']",

        # Resume
        "resume_input": "input[type='file'][name='resume'], input.resume-upload",
        "resume_button": "button.resume-upload-btn, [data-qa='resume-upload']",

        # Cover letter
        "cover_letter": "textarea[name='comments'], #additional-information",

        # Links
        "linkedin": "input[name*='linkedin'], input[placeholder*='LinkedIn']",
        "github": "input[name*='github'], input[placeholder*='GitHub']",
        "portfolio": "input[name*='portfolio'], input[name*='website']",

        # Submit
        "submit_button": "button[type='submit'], button.postings-btn, button:has-text('Submit')",

        # Confirmation
        "confirmation": ".application-confirmation, .thank-you-message, h1:has-text('Thanks'), h2:has-text('application')",

        # Apply button (on job page)
        "apply_button": "a.postings-btn, a:has-text('Apply'), button:has-text('Apply')",
    }

    async def _navigate_to_application(self, application_url: str):
        """Navigate to the Lever application page."""
        self.logger.info(f"Navigating to {application_url}")

        # Ensure URL ends with /apply
        if not application_url.endswith("/apply"):
            application_url = application_url.rstrip("/") + "/apply"

        await self._page.goto(application_url, wait_until="networkidle")
        await asyncio.sleep(1)

        # Wait for form to load
        await self._page.wait_for_selector(
            f"{self.SELECTORS['name']}, {self.SELECTORS['email']}",
            timeout=15000
        )

        self.logger.info("Application form loaded")

    async def _fill_application(
        self,
        profile: ApplicantProfile,
        resume_path: str,
        cover_letter_text: Optional[str],
    ):
        """Fill in the Lever application form."""
        self.logger.info("Filling Lever application form")

        # Full name (Lever typically uses single name field)
        full_name = f"{profile.first_name} {profile.last_name}"
        await self._fill_input(self.SELECTORS["name"], full_name)

        # Email
        await self._fill_input(self.SELECTORS["email"], profile.email)

        # Phone
        await self._fill_input(self.SELECTORS["phone"], profile.phone)

        # Location
        if profile.city and profile.state:
            location = f"{profile.city}, {profile.state}"
            await self._fill_input(self.SELECTORS["location"], location)

        # Current company
        if profile.current_company:
            await self._fill_input(self.SELECTORS["company"], profile.current_company)

        # Resume upload
        await self._upload_resume(resume_path)

        # Links
        if profile.linkedin_url:
            await self._fill_input(self.SELECTORS["linkedin"], profile.linkedin_url)

        if profile.github_url:
            await self._fill_input(self.SELECTORS["github"], profile.github_url)

        if profile.portfolio_url:
            await self._fill_input(self.SELECTORS["portfolio"], profile.portfolio_url)

        # Cover letter / Additional info
        if cover_letter_text:
            await self._fill_cover_letter(cover_letter_text)

        # Custom questions
        await self._fill_custom_questions(profile)

        # Work authorization questions
        await self._fill_work_auth(profile)

        self.logger.info("Form filled successfully")

    async def _upload_resume(self, resume_path: str):
        """Upload resume file."""
        self.logger.info("Uploading resume")

        # Try direct file input
        file_input = await self._page.query_selector(self.SELECTORS["resume_input"])
        if file_input:
            await file_input.set_input_files(resume_path)
            await asyncio.sleep(1)
            self.logger.info("Resume uploaded via file input")
            return

        # Try clicking upload button which may reveal file input
        upload_btn = await self._page.query_selector(self.SELECTORS["resume_button"])
        if upload_btn:
            await upload_btn.click()
            await asyncio.sleep(0.5)

            # Now try to find the file input
            file_input = await self._page.query_selector("input[type='file']")
            if file_input:
                await file_input.set_input_files(resume_path)
                await asyncio.sleep(1)
                self.logger.info("Resume uploaded after clicking button")
                return

        # Fallback: try any file input
        file_inputs = await self._page.query_selector_all("input[type='file']")
        for file_input in file_inputs:
            try:
                await file_input.set_input_files(resume_path)
                await asyncio.sleep(1)
                self.logger.info("Resume uploaded via fallback")
                return
            except Exception:
                continue

        self.logger.warning("Could not find resume upload field")

    async def _fill_cover_letter(self, cover_letter_text: str):
        """Fill cover letter / additional information."""
        self.logger.info("Filling cover letter")

        textarea = await self._page.query_selector(self.SELECTORS["cover_letter"])
        if textarea:
            await textarea.fill(cover_letter_text)
            self.logger.info("Cover letter filled")
        else:
            # Try finding any textarea for additional info
            textareas = await self._page.query_selector_all("textarea")
            for ta in textareas:
                placeholder = await ta.get_attribute("placeholder") or ""
                name = await ta.get_attribute("name") or ""
                if "additional" in placeholder.lower() or "comments" in name.lower():
                    await ta.fill(cover_letter_text)
                    self.logger.info("Cover letter filled in textarea")
                    return

            self.logger.debug("No cover letter field found")

    async def _fill_work_auth(self, profile: ApplicantProfile):
        """Fill work authorization questions in custom fields."""
        # Lever typically handles these as custom questions
        # Look for dropdowns or radios related to work auth

        selects = await self._page.query_selector_all("select")
        for select in selects:
            # Get associated label
            select_id = await select.get_attribute("id") or ""
            label_element = await self._page.query_selector(f"label[for='{select_id}']")
            label_text = ""
            if label_element:
                label_text = (await label_element.text_content() or "").lower()

            # Work authorization
            if "authorized" in label_text or "legally" in label_text:
                if profile.us_authorized:
                    await self._select_yes_no(select, profile.us_authorized == "yes")

            # Sponsorship
            if "sponsor" in label_text or "visa" in label_text:
                if profile.requires_sponsorship:
                    await self._select_yes_no(select, profile.requires_sponsorship == "yes")

    async def _select_yes_no(self, select_element, value: bool):
        """Select Yes or No in a dropdown."""
        try:
            options = await select_element.query_selector_all("option")
            target = "yes" if value else "no"

            for opt in options:
                opt_text = (await opt.text_content() or "").lower()
                if target in opt_text:
                    opt_value = await opt.get_attribute("value")
                    await select_element.select_option(value=opt_value)
                    return
        except Exception as e:
            self.logger.debug(f"Could not select yes/no: {e}")

    async def _fill_custom_questions(self, profile: ApplicantProfile):
        """Fill custom questions using stored answers."""
        if not profile.custom_answers:
            return

        # Find all form groups / questions
        form_groups = await self._page.query_selector_all(
            ".application-question, .custom-question, [class*='question']"
        )

        for group in form_groups:
            question_text = await group.text_content()
            if not question_text:
                continue

            question_lower = question_text.lower()

            # Check if we have an answer
            for pattern, answer in profile.custom_answers.items():
                if pattern.lower() in question_lower:
                    # Find input/textarea/select within this group
                    input_field = await group.query_selector("input, textarea, select")
                    if input_field:
                        tag = await input_field.evaluate("el => el.tagName")
                        if tag == "SELECT":
                            await self._select_best_option(input_field, answer)
                        else:
                            await input_field.fill(answer)
                        break

    async def _select_best_option(self, select_element, answer: str):
        """Select the best matching option."""
        try:
            options = await select_element.query_selector_all("option")
            answer_lower = answer.lower()

            # First try exact match
            for opt in options:
                opt_text = (await opt.text_content() or "").lower().strip()
                if opt_text == answer_lower:
                    opt_value = await opt.get_attribute("value")
                    await select_element.select_option(value=opt_value)
                    return

            # Then try partial match
            for opt in options:
                opt_text = (await opt.text_content() or "").lower()
                if answer_lower in opt_text or opt_text in answer_lower:
                    opt_value = await opt.get_attribute("value")
                    await select_element.select_option(value=opt_value)
                    return
        except Exception as e:
            self.logger.debug(f"Could not select option: {e}")

    async def _submit_form(self) -> Optional[str]:
        """Submit the application form."""
        self.logger.info("Submitting application")

        # Find submit button
        submit_button = await self._page.query_selector(self.SELECTORS["submit_button"])
        if not submit_button:
            raise Exception("Submit button not found")

        await submit_button.click()

        # Wait for confirmation
        try:
            await self._page.wait_for_selector(
                self.SELECTORS["confirmation"],
                timeout=30000
            )
            self.logger.info("Confirmation page loaded")
        except Exception:
            # Check for errors
            error = await self._page.query_selector(".error, .field-error, [class*='error']")
            if error:
                error_text = await error.text_content()
                raise Exception(f"Form error: {error_text}")
            raise Exception("No confirmation after submit")

        # Lever doesn't typically show a confirmation ID
        return None
