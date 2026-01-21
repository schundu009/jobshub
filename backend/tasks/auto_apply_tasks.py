"""
Celery Tasks for Auto-Apply Feature.

Tasks:
- submit_application: Submit a single job application
- process_pending_applications: Process queued applications
- reset_daily_application_counts: Reset daily counters at midnight
"""

import asyncio
import logging
import os
import tempfile
from datetime import datetime, date
from typing import Optional

from celery import shared_task
from sqlalchemy.orm import Session

from celery_app import celery_app
from database import SessionLocal
from models import (
    User, Job, Company, UserDocument, ApplicationSubmission,
    AutoApplyConfig, ApplicationAnswer
)
from services.auto_apply.base import ApplicantProfile, ApplyResult
from services.auto_apply.utils import get_ats_type_from_url, is_supported_ats

logger = logging.getLogger(__name__)


def get_db() -> Session:
    """Get a database session."""
    return SessionLocal()


def build_applicant_profile(user: User, db: Session) -> ApplicantProfile:
    """
    Build an ApplicantProfile from a User model.

    Args:
        user: User database model
        db: Database session for loading answers

    Returns:
        ApplicantProfile instance
    """
    # Load custom answers
    custom_answers = {}
    answers = db.query(ApplicationAnswer).filter(
        ApplicationAnswer.user_id == user.id,
        ApplicationAnswer.is_active == True
    ).all()
    for answer in answers:
        custom_answers[answer.question_pattern] = answer.answer_text

    return ApplicantProfile(
        first_name=user.first_name or "",
        last_name=user.last_name or "",
        email=user.email,
        phone=user.phone or "",
        address_line1=user.address_line1,
        address_line2=user.address_line2,
        city=user.city,
        state=user.state,
        postal_code=user.postal_code,
        country=user.address_country or user.country,
        us_authorized=user.us_authorized,
        requires_sponsorship=user.requires_sponsorship,
        linkedin_url=user.linkedin_url,
        github_url=user.github_url,
        portfolio_url=user.portfolio_url,
        gender=user.gender,
        ethnicity=user.ethnicity,
        veteran_status=user.veteran_status,
        disability_status=user.disability_status,
        custom_answers=custom_answers,
    )


def get_resume_path(user_id: int, resume_id: Optional[int], db: Session) -> Optional[str]:
    """
    Get the file path for a user's resume.

    Args:
        user_id: User ID
        resume_id: Specific resume ID or None for default
        db: Database session

    Returns:
        Path to resume file or None
    """
    if resume_id:
        doc = db.query(UserDocument).filter(
            UserDocument.id == resume_id,
            UserDocument.user_id == user_id
        ).first()
    else:
        # Get default resume
        doc = db.query(UserDocument).filter(
            UserDocument.user_id == user_id,
            UserDocument.document_type == "resume",
            UserDocument.is_default == True
        ).first()

        if not doc:
            # Get any resume
            doc = db.query(UserDocument).filter(
                UserDocument.user_id == user_id,
                UserDocument.document_type == "resume"
            ).first()

    if doc and doc.file_path and os.path.exists(doc.file_path):
        return doc.file_path

    # If no file path, try to create a temp file from content_text
    if doc and doc.content_text:
        # Create a simple text file with resume content
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"resume_{user_id}_{doc.id}.txt")
        with open(temp_path, 'w') as f:
            f.write(doc.content_text)
        return temp_path

    return None


@celery_app.task(bind=True, max_retries=2, default_retry_delay=120)
def submit_application(
    self,
    job_id: int,
    user_id: int,
    resume_id: Optional[int] = None,
    cover_letter_text: Optional[str] = None,
    use_ai_cover_letter: bool = False,
):
    """
    Submit a job application using browser automation.

    Args:
        job_id: Database job ID
        user_id: Database user ID
        resume_id: Optional specific resume ID
        cover_letter_text: Optional cover letter text
        use_ai_cover_letter: Generate cover letter using AI
    """
    db = get_db()

    try:
        # Get the submission record
        submission = db.query(ApplicationSubmission).filter(
            ApplicationSubmission.job_id == job_id,
            ApplicationSubmission.user_id == user_id,
            ApplicationSubmission.status == "pending"
        ).first()

        if not submission:
            logger.error(f"No pending submission found for job {job_id}, user {user_id}")
            return {"success": False, "error": "No pending submission found"}

        # Update status
        submission.status = "submitting"
        submission.started_at = datetime.utcnow()
        db.commit()

        # Load job and user
        job = db.query(Job).filter(Job.id == job_id).first()
        user = db.query(User).filter(User.id == user_id).first()

        if not job:
            submission.status = "failed"
            submission.error_message = "Job not found"
            db.commit()
            return {"success": False, "error": "Job not found"}

        if not user:
            submission.status = "failed"
            submission.error_message = "User not found"
            db.commit()
            return {"success": False, "error": "User not found"}

        # Check if ATS is supported
        if not job.job_url:
            submission.status = "failed"
            submission.error_message = "Job has no URL"
            db.commit()
            return {"success": False, "error": "Job has no URL"}

        ats_type = get_ats_type_from_url(job.job_url)
        if not ats_type or not is_supported_ats(job.job_url):
            submission.status = "failed"
            submission.error_message = f"Unsupported ATS type: {ats_type or 'unknown'}"
            db.commit()
            return {"success": False, "error": f"Unsupported ATS: {ats_type}"}

        submission.ats_type = ats_type
        submission.application_url = job.job_url
        db.commit()

        # Get resume path
        resume_path = get_resume_path(user.id, resume_id, db)
        if not resume_path:
            submission.status = "failed"
            submission.error_message = "No resume found"
            db.commit()
            return {"success": False, "error": "No resume found"}

        submission.resume_id = resume_id
        db.commit()

        # Generate cover letter if requested
        if use_ai_cover_letter and not cover_letter_text:
            try:
                from services.openai_service import generate_cover_letter
                company = db.query(Company).filter(Company.id == job.company_id).first()
                company_name = company.name if company else "the company"

                # Get resume text
                resume_doc = db.query(UserDocument).filter(
                    UserDocument.id == resume_id
                ).first() if resume_id else None
                resume_text = resume_doc.content_text if resume_doc else ""

                cover_letter_text = generate_cover_letter(
                    job_title=job.title,
                    company_name=company_name,
                    job_description=job.job_description or "",
                    resume_text=resume_text
                )
            except Exception as e:
                logger.warning(f"Failed to generate cover letter: {e}")

        submission.cover_letter_text = cover_letter_text
        db.commit()

        # Build applicant profile
        profile = build_applicant_profile(user, db)

        # Run the application submission (async)
        result = asyncio.run(
            _run_application_submission(
                ats_type=ats_type,
                job_id=job_id,
                user_id=user_id,
                application_url=job.job_url,
                profile=profile,
                resume_path=resume_path,
                cover_letter_text=cover_letter_text,
            )
        )

        # Update submission record
        if result.success:
            submission.status = "success"
            submission.ats_confirmation_id = result.confirmation_id
            submission.confirmation_screenshot = result.screenshot_path
        else:
            submission.status = "failed"
            submission.error_message = result.error_message
            submission.confirmation_screenshot = result.screenshot_path
            submission.retry_count = (submission.retry_count or 0) + 1

        submission.completed_at = datetime.utcnow()
        db.commit()

        return {
            "success": result.success,
            "job_id": job_id,
            "confirmation_id": result.confirmation_id,
            "error": result.error_message,
        }

    except Exception as e:
        logger.exception(f"Error submitting application for job {job_id}")

        # Update submission status
        submission = db.query(ApplicationSubmission).filter(
            ApplicationSubmission.job_id == job_id,
            ApplicationSubmission.user_id == user_id
        ).first()
        if submission:
            submission.status = "failed"
            submission.error_message = str(e)
            submission.completed_at = datetime.utcnow()
            db.commit()

        # Retry if not max retries
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)

        return {"success": False, "error": str(e)}

    finally:
        db.close()


async def _run_application_submission(
    ats_type: str,
    job_id: int,
    user_id: int,
    application_url: str,
    profile: ApplicantProfile,
    resume_path: str,
    cover_letter_text: Optional[str],
) -> ApplyResult:
    """
    Run the actual application submission with browser automation.

    This is an async function that runs in an event loop.
    """
    from scrapers.browser_pool import BrowserPool

    # Get browser pool
    browser_pool = BrowserPool()
    await browser_pool.start()

    try:
        # Get the appropriate applicant handler
        if ats_type == "greenhouse":
            from services.auto_apply.greenhouse import GreenhouseApplicant
            applicant = GreenhouseApplicant(browser_pool=browser_pool)
        elif ats_type == "lever":
            from services.auto_apply.lever import LeverApplicant
            applicant = LeverApplicant(browser_pool=browser_pool)
        else:
            return ApplyResult(
                success=False,
                job_id=job_id,
                user_id=user_id,
                ats_type=ats_type,
                application_url=application_url,
                error_message=f"Unsupported ATS type: {ats_type}",
            )

        # Submit the application
        result = await applicant.submit_application(
            job_id=job_id,
            user_id=user_id,
            application_url=application_url,
            profile=profile,
            resume_path=resume_path,
            cover_letter_text=cover_letter_text,
        )

        return result

    finally:
        await browser_pool.stop()


@celery_app.task
def process_pending_applications():
    """
    Process pending applications from the queue.

    This task runs periodically to pick up queued applications
    and submit them.
    """
    db = get_db()

    try:
        # Get pending submissions
        pending = db.query(ApplicationSubmission).filter(
            ApplicationSubmission.status == "pending"
        ).order_by(ApplicationSubmission.queued_at).limit(10).all()

        logger.info(f"Found {len(pending)} pending applications")

        for submission in pending:
            # Check user's daily limit
            config = db.query(AutoApplyConfig).filter(
                AutoApplyConfig.user_id == submission.user_id
            ).first()

            if config:
                # Reset counter if new day
                today = date.today()
                if config.last_reset_date != today:
                    config.applications_today = 0
                    config.last_reset_date = today
                    db.commit()

                # Check limit
                if config.applications_today >= config.daily_limit:
                    logger.info(
                        f"User {submission.user_id} reached daily limit "
                        f"({config.daily_limit})"
                    )
                    continue

                # Increment counter
                config.applications_today += 1
                db.commit()

            # Queue the submission task
            submit_application.delay(
                job_id=submission.job_id,
                user_id=submission.user_id,
                resume_id=submission.resume_id,
                cover_letter_text=submission.cover_letter_text,
            )

        return {"processed": len(pending)}

    finally:
        db.close()


@celery_app.task
def reset_daily_application_counts():
    """
    Reset daily application counters at midnight.

    This task runs daily to reset the applications_today counter
    for all users.
    """
    db = get_db()

    try:
        today = date.today()

        # Reset all counters where last_reset_date is not today
        count = db.query(AutoApplyConfig).filter(
            AutoApplyConfig.last_reset_date != today
        ).update({
            AutoApplyConfig.applications_today: 0,
            AutoApplyConfig.last_reset_date: today,
        })

        db.commit()
        logger.info(f"Reset daily application counts for {count} users")

        return {"reset_count": count}

    finally:
        db.close()
