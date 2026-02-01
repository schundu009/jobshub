"""
Auto-Apply API Routes.

Endpoints for managing auto-apply configuration, submissions, and history.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date

from database import get_db
from models import (
    User, Job, Company, AutoApplyConfig, ApplicationSubmission,
    ApplicationAnswer, UserDocument
)
from middleware.auth import get_current_user
from services.auto_apply.utils import (
    get_ats_type_from_url, is_supported_ats, validate_profile_completeness
)

router = APIRouter(prefix="/api/auto-apply", tags=["auto-apply"])


# ============== Pydantic Schemas ==============

class AutoApplyConfigUpdate(BaseModel):
    """Schema for updating auto-apply configuration."""
    enabled: Optional[bool] = None
    daily_limit: Optional[int] = Field(None, ge=1, le=50)
    min_relevance_score: Optional[float] = Field(None, ge=0, le=100)
    default_resume_id: Optional[int] = None
    default_cover_letter_id: Optional[int] = None
    use_ai_cover_letter: Optional[bool] = None
    excluded_companies: Optional[List[str]] = None
    supported_ats: Optional[List[str]] = None
    # Workday credentials
    workday_email: Optional[str] = Field(None, max_length=255)
    workday_password: Optional[str] = Field(None, max_length=255)  # Will be encrypted


class ApplicationAnswerCreate(BaseModel):
    """Schema for creating a reusable answer."""
    question_pattern: str = Field(..., min_length=3, max_length=500)
    question_category: Optional[str] = Field(None, max_length=50)
    answer_text: str = Field(..., min_length=1)
    answer_type: str = Field("text", max_length=20)
    priority: int = Field(0, ge=0, le=100)


class ApplicationAnswerUpdate(BaseModel):
    """Schema for updating a reusable answer."""
    question_pattern: Optional[str] = Field(None, min_length=3, max_length=500)
    question_category: Optional[str] = Field(None, max_length=50)
    answer_text: Optional[str] = Field(None, min_length=1)
    answer_type: Optional[str] = Field(None, max_length=20)
    priority: Optional[int] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None


class SubmitApplicationRequest(BaseModel):
    """Schema for submitting an application."""
    resume_id: Optional[int] = None
    cover_letter_text: Optional[str] = None
    use_ai_cover_letter: bool = False
    process_immediately: bool = False  # Process now instead of queuing to Celery


class BulkSubmitRequest(BaseModel):
    """Schema for bulk application submission."""
    job_ids: List[int] = Field(..., min_items=1, max_items=20)
    resume_id: Optional[int] = None
    use_ai_cover_letter: bool = True


# ============== Config Endpoints ==============

@router.get("/config")
def get_auto_apply_config(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's auto-apply configuration."""
    config = db.query(AutoApplyConfig).filter(
        AutoApplyConfig.user_id == current_user.id
    ).first()

    if not config:
        # Return defaults
        return {
            "enabled": False,
            "daily_limit": 10,
            "applications_today": 0,
            "min_relevance_score": 50.0,
            "default_resume_id": None,
            "default_cover_letter_id": None,
            "use_ai_cover_letter": True,
            "excluded_companies": [],
            "supported_ats": ["greenhouse", "lever", "workday"],
            "workday_email": None,
            "workday_configured": False,
        }

    return {
        "enabled": config.enabled,
        "daily_limit": config.daily_limit,
        "applications_today": config.applications_today,
        "min_relevance_score": config.min_relevance_score,
        "default_resume_id": config.default_resume_id,
        "default_cover_letter_id": config.default_cover_letter_id,
        "use_ai_cover_letter": config.use_ai_cover_letter,
        "excluded_companies": config.excluded_companies or [],
        "supported_ats": config.supported_ats or ["greenhouse", "lever", "workday"],
        "workday_email": config.workday_email,
        "workday_configured": bool(config.workday_email and config.workday_password_encrypted),
    }


@router.put("/config")
def update_auto_apply_config(
    config_data: AutoApplyConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user's auto-apply configuration."""
    config = db.query(AutoApplyConfig).filter(
        AutoApplyConfig.user_id == current_user.id
    ).first()

    if not config:
        config = AutoApplyConfig(user_id=current_user.id)
        db.add(config)

    # Update fields
    update_data = config_data.model_dump(exclude_unset=True)

    # Handle Workday password encryption
    if "workday_password" in update_data:
        workday_password = update_data.pop("workday_password")
        if workday_password:
            from services.encryption import encrypt_password
            config.workday_password_encrypted = encrypt_password(workday_password)
        else:
            # Clear password if empty string provided
            config.workday_password_encrypted = None

    for field, value in update_data.items():
        if hasattr(config, field):
            setattr(config, field, value)

    db.commit()
    db.refresh(config)

    return {"message": "Configuration updated successfully"}


@router.post("/reset-daily-counter")
def reset_daily_counter(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reset the user's daily application counter to 0."""
    config = db.query(AutoApplyConfig).filter(
        AutoApplyConfig.user_id == current_user.id
    ).first()

    if not config:
        return {"message": "No config found, nothing to reset", "applications_today": 0}

    config.applications_today = 0
    config.last_reset_date = date.today()
    db.commit()

    return {
        "message": "Daily counter reset successfully",
        "applications_today": 0,
        "daily_limit": config.daily_limit
    }


@router.post("/process-queue")
def process_application_queue(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually trigger processing of pending applications."""
    # Get pending submissions for this user
    pending = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.user_id == current_user.id,
        ApplicationSubmission.status == "pending"
    ).all()

    if not pending:
        return {"message": "No pending applications to process", "queued": 0}

    queued_count = 0
    for submission in pending:
        try:
            # Try Celery first, fall back to direct processing note
            try:
                from tasks.auto_apply_tasks import submit_application as submit_task
                submit_task.delay(
                    job_id=submission.job_id,
                    user_id=current_user.id,
                    resume_id=submission.resume_id,
                    cover_letter_text=submission.cover_letter_text,
                    use_ai_cover_letter=False,
                )
                queued_count += 1
            except Exception as celery_error:
                # Celery not available - mark for manual processing
                submission.error_message = f"Celery unavailable. Use /process-now endpoint. Error: {str(celery_error)}"
                db.commit()
        except Exception as e:
            # Mark as failed if we can't queue
            submission.status = "failed"
            submission.error_message = f"Failed to queue: {str(e)}"
            db.commit()

    return {
        "message": f"Queued {queued_count} applications for processing",
        "queued": queued_count,
        "total_pending": len(pending),
        "note": "If Celery workers are not running, use POST /api/auto-apply/process-now/{submission_id} to process directly"
    }


@router.post("/process-now/{submission_id}")
async def process_submission_now(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Process a single submission immediately without Celery.

    This endpoint runs the browser automation synchronously, so it may take 30-60 seconds.
    Use this when Celery workers are not available.
    """
    import asyncio
    from services.auto_apply.utils import get_ats_type_from_url

    # Get the submission
    submission = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.id == submission_id,
        ApplicationSubmission.user_id == current_user.id
    ).first()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status not in ["pending", "failed"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot process submission with status: {submission.status}"
        )

    # Get the job
    job = db.query(Job).filter(Job.id == submission.job_id).first()
    if not job:
        submission.status = "failed"
        submission.error_message = "Job not found"
        submission.completed_at = datetime.utcnow()
        db.commit()
        raise HTTPException(status_code=404, detail="Job not found")

    # Update status to submitting
    submission.status = "submitting"
    submission.started_at = datetime.utcnow()
    submission.error_message = None  # Clear previous error
    db.commit()

    try:
        # Run the submission process
        result = await _process_submission_async(
            submission=submission,
            job=job,
            user=current_user,
            db=db
        )

        return {
            "success": result["success"],
            "submission_id": submission_id,
            "status": submission.status,
            "confirmation_id": result.get("confirmation_id"),
            "error": result.get("error"),
            "message": "Application submitted successfully" if result["success"] else f"Application failed: {result.get('error')}"
        }

    except Exception as e:
        submission.status = "failed"
        submission.error_message = str(e)
        submission.completed_at = datetime.utcnow()
        db.commit()

        return {
            "success": False,
            "submission_id": submission_id,
            "status": "failed",
            "error": str(e),
            "message": f"Application failed: {str(e)}"
        }


async def _process_submission_async(
    submission: ApplicationSubmission,
    job: Job,
    user: User,
    db: Session
) -> dict:
    """
    Process a submission using browser automation.

    This is the core logic extracted from the Celery task.
    """
    import os
    import tempfile
    from services.auto_apply.utils import get_ats_type_from_url, is_supported_ats
    from services.auto_apply.base import ApplicantProfile
    from models import Company, AutoApplyConfig, ApplicationAnswer, UserDocument

    # Check ATS support
    if not job.job_url:
        submission.status = "failed"
        submission.error_message = "Job has no URL"
        submission.completed_at = datetime.utcnow()
        db.commit()
        return {"success": False, "error": "Job has no URL"}

    ats_type = get_ats_type_from_url(job.job_url)
    if not ats_type or not is_supported_ats(job.job_url):
        submission.status = "failed"
        submission.error_message = f"Unsupported ATS type: {ats_type or 'unknown'}"
        submission.completed_at = datetime.utcnow()
        db.commit()
        return {"success": False, "error": f"Unsupported ATS: {ats_type}"}

    submission.ats_type = ats_type
    submission.application_url = job.job_url
    db.commit()

    # Get resume path
    resume_path = _get_resume_path_sync(user.id, submission.resume_id, db)
    if not resume_path:
        submission.status = "failed"
        submission.error_message = "No resume found. Please upload a resume first."
        submission.completed_at = datetime.utcnow()
        db.commit()
        return {"success": False, "error": "No resume found"}

    # Build applicant profile
    custom_answers = {}
    answers = db.query(ApplicationAnswer).filter(
        ApplicationAnswer.user_id == user.id,
        ApplicationAnswer.is_active == True
    ).all()
    for answer in answers:
        custom_answers[answer.question_pattern] = answer.answer_text

    profile = ApplicantProfile(
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

    # Get Workday credentials if needed
    workday_email = None
    workday_password = None
    if ats_type == "workday":
        config = db.query(AutoApplyConfig).filter(
            AutoApplyConfig.user_id == user.id
        ).first()
        if config and config.workday_email:
            workday_email = config.workday_email
            if config.workday_password_encrypted:
                try:
                    from services.encryption import decrypt_password
                    workday_password = decrypt_password(config.workday_password_encrypted)
                except Exception:
                    pass

    # Run the browser automation
    try:
        from services.browser_pool import BrowserPool

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
            elif ats_type == "workday":
                from services.auto_apply.workday import WorkdayApplicant
                applicant = WorkdayApplicant(
                    browser_pool=browser_pool,
                    workday_email=workday_email,
                    workday_password=workday_password,
                )
            else:
                submission.status = "failed"
                submission.error_message = f"Unsupported ATS type: {ats_type}"
                submission.completed_at = datetime.utcnow()
                db.commit()
                return {"success": False, "error": f"Unsupported ATS: {ats_type}"}

            # Submit the application
            result = await applicant.submit_application(
                job_id=job.id,
                user_id=user.id,
                application_url=job.job_url,
                profile=profile,
                resume_path=resume_path,
                cover_letter_text=submission.cover_letter_text,
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
                "confirmation_id": result.confirmation_id,
                "error": result.error_message,
            }

        finally:
            await browser_pool.stop()

    except Exception as e:
        submission.status = "failed"
        submission.error_message = f"Browser automation error: {str(e)}"
        submission.completed_at = datetime.utcnow()
        db.commit()
        return {"success": False, "error": str(e)}


def _get_resume_path_sync(user_id: int, resume_id: Optional[int], db: Session) -> Optional[str]:
    """Get the file path for a user's resume."""
    import os
    import tempfile

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
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, f"resume_{user_id}_{doc.id}.txt")
        with open(temp_path, 'w') as f:
            f.write(doc.content_text)
        return temp_path

    return None


@router.post("/process-all")
async def process_all_pending(
    limit: int = Query(5, ge=1, le=20, description="Max submissions to process"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Process all pending submissions for the current user.

    This processes submissions one by one without Celery.
    Use this when Celery workers are not available.

    Note: This may take a long time (30-60 seconds per submission).
    """
    # Get pending submissions
    pending = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.user_id == current_user.id,
        ApplicationSubmission.status == "pending"
    ).order_by(ApplicationSubmission.queued_at).limit(limit).all()

    if not pending:
        return {
            "message": "No pending applications to process",
            "processed": 0,
            "results": []
        }

    results = []
    for submission in pending:
        job = db.query(Job).filter(Job.id == submission.job_id).first()
        if not job:
            submission.status = "failed"
            submission.error_message = "Job not found"
            submission.completed_at = datetime.utcnow()
            db.commit()
            results.append({
                "submission_id": submission.id,
                "job_id": submission.job_id,
                "success": False,
                "error": "Job not found"
            })
            continue

        try:
            result = await _process_submission_async(
                submission=submission,
                job=job,
                user=current_user,
                db=db
            )
            results.append({
                "submission_id": submission.id,
                "job_id": submission.job_id,
                "job_title": job.title,
                "success": result["success"],
                "confirmation_id": result.get("confirmation_id"),
                "error": result.get("error"),
                "status": submission.status
            })
        except Exception as e:
            submission.status = "failed"
            submission.error_message = str(e)
            submission.completed_at = datetime.utcnow()
            db.commit()
            results.append({
                "submission_id": submission.id,
                "job_id": submission.job_id,
                "job_title": job.title,
                "success": False,
                "error": str(e),
                "status": "failed"
            })

    successful = sum(1 for r in results if r["success"])
    failed = len(results) - successful

    return {
        "message": f"Processed {len(results)} applications: {successful} successful, {failed} failed",
        "processed": len(results),
        "successful": successful,
        "failed": failed,
        "results": results
    }


@router.delete("/clear-queue")
def clear_queue(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete all pending submissions for the current user."""
    deleted = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.user_id == current_user.id,
        ApplicationSubmission.status.in_(["pending", "failed", "skipped"])
    ).delete(synchronize_session=False)
    db.commit()

    return {"message": f"Cleared {deleted} submissions from queue", "deleted": deleted}


@router.delete("/submission/{submission_id}")
def cancel_submission(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel/delete a pending submission."""
    submission = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.id == submission_id,
        ApplicationSubmission.user_id == current_user.id
    ).first()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status not in ["pending", "failed", "skipped"]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel submission with status: {submission.status}"
        )

    db.delete(submission)
    db.commit()

    return {"message": "Submission cancelled", "id": submission_id}


@router.get("/preflight/{job_id}")
def preflight_check(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Check if auto-apply is possible for a job.

    Returns profile completeness and ATS compatibility.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check ATS support
    ats_type = get_ats_type_from_url(job.job_url) if job.job_url else None
    ats_supported = is_supported_ats(job.job_url) if job.job_url else False

    # Check profile completeness
    profile_data = {
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "email": current_user.email,
        "phone": current_user.phone,
        "city": current_user.city,
        "state": current_user.state,
        "linkedin_url": current_user.linkedin_url,
        "us_authorized": current_user.us_authorized,
        "requires_sponsorship": current_user.requires_sponsorship,
    }
    profile_check = validate_profile_completeness(profile_data)

    # Check for resume
    has_resume = db.query(UserDocument).filter(
        UserDocument.user_id == current_user.id,
        UserDocument.document_type == "resume"
    ).count() > 0

    # Get config
    config = db.query(AutoApplyConfig).filter(
        AutoApplyConfig.user_id == current_user.id
    ).first()

    # Check daily limit
    daily_limit_reached = False
    if config:
        today = date.today()
        if config.last_reset_date == today:
            daily_limit_reached = config.applications_today >= config.daily_limit

    # Check for existing submission - only block for pending/submitting/success
    # Allow re-application for failed or skipped jobs
    existing_submission = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.job_id == job_id,
        ApplicationSubmission.user_id == current_user.id,
        ApplicationSubmission.status.in_(["pending", "submitting", "success"])
    ).first()

    # Get resumes for selection
    resumes = db.query(UserDocument).filter(
        UserDocument.user_id == current_user.id,
        UserDocument.document_type == "resume"
    ).all()

    resume_list = [
        {
            "id": r.id,
            "name": r.filename or f"Resume {r.id}",
            "is_default": r.is_default or False
        }
        for r in resumes
    ]

    # Get daily limit info
    daily_limit = config.daily_limit if config else 10
    applications_today = config.applications_today if config else 0

    return {
        "can_apply": (
            ats_supported and
            profile_check["all_required_complete"] and
            has_resume and
            not daily_limit_reached and
            not existing_submission
        ),
        "job": {
            "id": job.id,
            "title": job.title,
            "job_url": job.job_url,
        },
        # Flat fields for frontend compatibility
        "ats_type": ats_type,
        "ats_supported": ats_supported,
        "profile_complete": profile_check["all_required_complete"],
        "profile_missing": profile_check.get("missing_fields", []),
        "resumes": resume_list,
        "daily_limit": daily_limit,
        "applications_today": applications_today,
        "daily_limit_reached": daily_limit_reached,
        "already_submitted": existing_submission is not None,
        "existing_submission_status": existing_submission.status if existing_submission else None,
    }


# ============== Submission Endpoints ==============

@router.post("/submit/{job_id}")
async def submit_application(
    job_id: int,
    request: SubmitApplicationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Queue a job application for submission.

    If process_immediately=True, the application will be processed right away.
    Otherwise, it will be queued for background processing (requires Celery workers).
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check ATS support
    if not job.job_url:
        raise HTTPException(status_code=400, detail="Job has no URL")

    ats_type = get_ats_type_from_url(job.job_url)
    if not ats_type or not is_supported_ats(job.job_url):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported ATS type: {ats_type or 'unknown'}. Supported: Greenhouse, Lever, Workday."
        )

    # Check for existing submission
    existing = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.job_id == job_id,
        ApplicationSubmission.user_id == current_user.id
    ).first()

    if existing:
        if existing.status in ["pending", "submitting", "success"]:
            raise HTTPException(
                status_code=400,
                detail=f"Application already {existing.status} for this job"
            )
        # Delete failed/skipped submissions so we can create a fresh one
        db.delete(existing)
        db.commit()

    # Create submission record
    submission = ApplicationSubmission(
        job_id=job_id,
        user_id=current_user.id,
        status="pending",
        ats_type=ats_type,
        application_url=job.job_url,
        resume_id=request.resume_id,
        cover_letter_text=request.cover_letter_text,
    )
    db.add(submission)
    db.commit()
    db.refresh(submission)

    # Process immediately if requested (bypasses Celery)
    if request.process_immediately:
        try:
            result = await _process_submission_async(
                submission=submission,
                job=job,
                user=current_user,
                db=db
            )
            return {
                "message": "Application submitted" if result["success"] else f"Application failed: {result.get('error')}",
                "submission_id": submission.id,
                "status": submission.status,
                "success": result["success"],
                "confirmation_id": result.get("confirmation_id"),
                "error": result.get("error"),
            }
        except Exception as e:
            submission.status = "failed"
            submission.error_message = str(e)
            submission.completed_at = datetime.utcnow()
            db.commit()
            return {
                "message": f"Application failed: {str(e)}",
                "submission_id": submission.id,
                "status": "failed",
                "success": False,
                "error": str(e),
            }

    # Queue the Celery task (fallback to note if Celery unavailable)
    try:
        from tasks.auto_apply_tasks import submit_application as submit_task
        submit_task.delay(
            job_id=job_id,
            user_id=current_user.id,
            resume_id=request.resume_id,
            cover_letter_text=request.cover_letter_text,
            use_ai_cover_letter=request.use_ai_cover_letter,
        )
        return {
            "message": "Application queued for submission",
            "submission_id": submission.id,
            "status": "pending",
        }
    except Exception as celery_error:
        # Celery not available - return submission ID so user can process manually
        return {
            "message": "Application created but Celery workers unavailable. Use process_immediately=true or call /process-now endpoint.",
            "submission_id": submission.id,
            "status": "pending",
            "celery_error": str(celery_error),
            "hint": f"POST /api/auto-apply/process-now/{submission.id} to process immediately"
        }


@router.post("/skip/{job_id}")
def skip_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Skip a job from the auto-apply queue.

    Creates a submission record with status 'skipped' to track that
    the user has seen and declined this job.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Check for existing submission
    existing = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.job_id == job_id,
        ApplicationSubmission.user_id == current_user.id
    ).first()

    if existing:
        if existing.status == 'skipped':
            return {"message": "Job already skipped", "status": "skipped"}
        raise HTTPException(
            status_code=400,
            detail=f"Job already has status: {existing.status}"
        )

    # Create a skipped submission record
    submission = ApplicationSubmission(
        job_id=job_id,
        user_id=current_user.id,
        status="skipped",
        ats_type=get_ats_type_from_url(job.job_url) if job.job_url else None,
        application_url=job.job_url,
    )
    db.add(submission)
    db.commit()

    return {
        "message": "Job skipped",
        "submission_id": submission.id,
        "status": "skipped",
    }


@router.post("/bulk-submit")
def bulk_submit_applications(
    request: BulkSubmitRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Queue multiple job applications for submission.
    """
    results = []

    for job_id in request.job_ids:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            results.append({"job_id": job_id, "status": "error", "error": "Job not found"})
            continue

        if not job.job_url or not is_supported_ats(job.job_url):
            results.append({"job_id": job_id, "status": "error", "error": "Unsupported ATS"})
            continue

        # Check for existing submission
        existing = db.query(ApplicationSubmission).filter(
            ApplicationSubmission.job_id == job_id,
            ApplicationSubmission.user_id == current_user.id
        ).first()

        if existing:
            results.append({
                "job_id": job_id,
                "status": "skipped",
                "error": f"Already {existing.status}"
            })
            continue

        # Create submission
        ats_type = get_ats_type_from_url(job.job_url)
        submission = ApplicationSubmission(
            job_id=job_id,
            user_id=current_user.id,
            status="pending",
            ats_type=ats_type,
            application_url=job.job_url,
            resume_id=request.resume_id,
        )
        db.add(submission)
        db.commit()

        # Queue task
        from tasks.auto_apply_tasks import submit_application as submit_task
        submit_task.delay(
            job_id=job_id,
            user_id=current_user.id,
            resume_id=request.resume_id,
            use_ai_cover_letter=request.use_ai_cover_letter,
        )

        results.append({
            "job_id": job_id,
            "status": "queued",
            "submission_id": submission.id
        })

    queued_count = sum(1 for r in results if r["status"] == "queued")
    return {
        "message": f"Queued {queued_count} applications",
        "results": results,
    }


@router.get("/submissions")
def list_submissions(
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List user's application submissions."""
    query = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.user_id == current_user.id
    )

    if status:
        query = query.filter(ApplicationSubmission.status == status)

    total = query.count()
    submissions = query.order_by(
        ApplicationSubmission.created_at.desc()
    ).offset(offset).limit(limit).all()

    results = []
    for s in submissions:
        job = db.query(Job).filter(Job.id == s.job_id).first()
        company = None
        if job and job.company_id:
            company = db.query(Company).filter(Company.id == job.company_id).first()

        results.append({
            "id": s.id,
            "job_id": s.job_id,
            "title": job.title if job else "Unknown",
            "job_title": job.title if job else "Unknown",  # Keep for backward compatibility
            "company_name": company.name if company else "Unknown",
            "location": job.location if job else None,
            "status": s.status,
            "ats_type": s.ats_type,
            "source": s.ats_type,  # Alias for frontend
            "application_url": s.application_url,
            "confirmation_id": s.ats_confirmation_id,
            "error_message": s.error_message,
            "created_at": s.created_at.isoformat() if s.created_at else None,
            "queued_at": s.queued_at.isoformat() if s.queued_at else None,
            "started_at": s.started_at.isoformat() if s.started_at else None,
            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
            "applied_at": s.completed_at.isoformat() if s.completed_at else (s.created_at.isoformat() if s.created_at else None),
        })

    return {
        "submissions": results,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/submissions/{submission_id}")
def get_submission(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get details of a specific submission."""
    submission = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.id == submission_id,
        ApplicationSubmission.user_id == current_user.id
    ).first()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    job = db.query(Job).filter(Job.id == submission.job_id).first()
    company = None
    if job and job.company_id:
        company = db.query(Company).filter(Company.id == job.company_id).first()

    return {
        "id": submission.id,
        "job": {
            "id": job.id if job else None,
            "title": job.title if job else "Unknown",
            "job_url": job.job_url if job else None,
        },
        "company": {
            "id": company.id if company else None,
            "name": company.name if company else "Unknown",
        },
        "status": submission.status,
        "ats_type": submission.ats_type,
        "application_url": submission.application_url,
        "resume_id": submission.resume_id,
        "cover_letter_text": submission.cover_letter_text,
        "confirmation_id": submission.ats_confirmation_id,
        "confirmation_screenshot": submission.confirmation_screenshot,
        "error_message": submission.error_message,
        "retry_count": submission.retry_count,
        "queued_at": submission.queued_at,
        "started_at": submission.started_at,
        "completed_at": submission.completed_at,
    }


@router.delete("/submissions/{submission_id}")
def cancel_submission(
    submission_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Cancel a pending submission."""
    submission = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.id == submission_id,
        ApplicationSubmission.user_id == current_user.id
    ).first()

    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")

    if submission.status != "pending":
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel submission with status: {submission.status}"
        )

    submission.status = "cancelled"
    db.commit()

    return {"message": "Submission cancelled"}


# ============== Answer Templates Endpoints ==============

@router.get("/answers")
def list_application_answers(
    category: Optional[str] = Query(None, description="Filter by category"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List user's reusable application answers."""
    query = db.query(ApplicationAnswer).filter(
        ApplicationAnswer.user_id == current_user.id
    )

    if category:
        query = query.filter(ApplicationAnswer.question_category == category)

    answers = query.order_by(
        ApplicationAnswer.priority.desc(),
        ApplicationAnswer.created_at.desc()
    ).all()

    return {
        "answers": [
            {
                "id": a.id,
                "question_pattern": a.question_pattern,
                "question_category": a.question_category,
                "answer_text": a.answer_text,
                "answer_type": a.answer_type,
                "priority": a.priority,
                "is_active": a.is_active,
                "created_at": a.created_at,
            }
            for a in answers
        ],
        "total": len(answers),
    }


@router.post("/answers")
def create_application_answer(
    answer_data: ApplicationAnswerCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a reusable application answer."""
    answer = ApplicationAnswer(
        user_id=current_user.id,
        question_pattern=answer_data.question_pattern,
        question_category=answer_data.question_category,
        answer_text=answer_data.answer_text,
        answer_type=answer_data.answer_type,
        priority=answer_data.priority,
    )
    db.add(answer)
    db.commit()
    db.refresh(answer)

    return {
        "message": "Answer created successfully",
        "id": answer.id,
    }


@router.put("/answers/{answer_id}")
def update_application_answer(
    answer_id: int,
    answer_data: ApplicationAnswerUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update a reusable application answer."""
    answer = db.query(ApplicationAnswer).filter(
        ApplicationAnswer.id == answer_id,
        ApplicationAnswer.user_id == current_user.id
    ).first()

    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    update_data = answer_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(answer, field):
            setattr(answer, field, value)

    db.commit()

    return {"message": "Answer updated successfully"}


@router.delete("/answers/{answer_id}")
def delete_application_answer(
    answer_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a reusable application answer."""
    answer = db.query(ApplicationAnswer).filter(
        ApplicationAnswer.id == answer_id,
        ApplicationAnswer.user_id == current_user.id
    ).first()

    if not answer:
        raise HTTPException(status_code=404, detail="Answer not found")

    db.delete(answer)
    db.commit()

    return {"message": "Answer deleted successfully"}
