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
            "supported_ats": ["greenhouse", "lever"],
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
        "supported_ats": config.supported_ats or ["greenhouse", "lever"],
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
    for field, value in update_data.items():
        if hasattr(config, field):
            setattr(config, field, value)

    db.commit()
    db.refresh(config)

    return {"message": "Configuration updated successfully"}


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

    # Check for existing submission
    existing_submission = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.job_id == job_id,
        ApplicationSubmission.user_id == current_user.id
    ).first()

    # Get resumes for selection
    resumes = db.query(UserDocument).filter(
        UserDocument.user_id == current_user.id,
        UserDocument.document_type == "resume"
    ).all()

    resume_list = [
        {
            "id": r.id,
            "name": r.file_name or r.original_filename or f"Resume {r.id}",
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
def submit_application(
    job_id: int,
    request: SubmitApplicationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Queue a job application for submission.

    The application will be processed by a background task.
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
            detail=f"Unsupported ATS type: {ats_type or 'unknown'}. Only Greenhouse and Lever are supported."
        )

    # Check for existing submission
    existing = db.query(ApplicationSubmission).filter(
        ApplicationSubmission.job_id == job_id,
        ApplicationSubmission.user_id == current_user.id
    ).first()

    if existing and existing.status in ["pending", "submitting", "success"]:
        raise HTTPException(
            status_code=400,
            detail=f"Application already {existing.status} for this job"
        )

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

    # Queue the Celery task
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
            "job_title": job.title if job else "Unknown",
            "company_name": company.name if company else "Unknown",
            "status": s.status,
            "ats_type": s.ats_type,
            "application_url": s.application_url,
            "confirmation_id": s.ats_confirmation_id,
            "error_message": s.error_message,
            "queued_at": s.queued_at,
            "started_at": s.started_at,
            "completed_at": s.completed_at,
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
