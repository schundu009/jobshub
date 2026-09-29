"""
Interview management routes with input validation.

Security features:
- Input length limits
- Enum validation for interview types and outcomes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime

from database import get_db
from models import Interview, Job, User
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/interviews", tags=["interviews"])

# Valid interview types
VALID_INTERVIEW_TYPES = {"phone_screen", "technical", "behavioral", "onsite", "panel", "hr", "final", "other"}

# Valid outcomes
VALID_OUTCOMES = {"pending", "passed", "failed", "cancelled", "no_show"}


class InterviewCreate(BaseModel):
    job_id: int = Field(..., ge=1)
    interview_date: datetime
    interview_type: Optional[str] = Field(None, max_length=50)
    interviewer_names: Optional[str] = Field(None, max_length=500)
    location: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=10000)
    outcome: Optional[str] = Field("pending", max_length=50)

    @field_validator('interview_type')
    @classmethod
    def validate_interview_type(cls, v):
        if v and v not in VALID_INTERVIEW_TYPES:
            raise ValueError(f"Invalid interview type. Must be one of: {', '.join(VALID_INTERVIEW_TYPES)}")
        return v

    @field_validator('outcome')
    @classmethod
    def validate_outcome(cls, v):
        if v and v not in VALID_OUTCOMES:
            raise ValueError(f"Invalid outcome. Must be one of: {', '.join(VALID_OUTCOMES)}")
        return v


class InterviewUpdate(BaseModel):
    interview_date: Optional[datetime] = None
    interview_type: Optional[str] = Field(None, max_length=50)
    interviewer_names: Optional[str] = Field(None, max_length=500)
    location: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=10000)
    outcome: Optional[str] = Field(None, max_length=50)

    @field_validator('interview_type')
    @classmethod
    def validate_interview_type(cls, v):
        if v and v not in VALID_INTERVIEW_TYPES:
            raise ValueError(f"Invalid interview type. Must be one of: {', '.join(VALID_INTERVIEW_TYPES)}")
        return v

    @field_validator('outcome')
    @classmethod
    def validate_outcome(cls, v):
        if v and v not in VALID_OUTCOMES:
            raise ValueError(f"Invalid outcome. Must be one of: {', '.join(VALID_OUTCOMES)}")
        return v


@router.get("")
def get_all_interviews(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get interviews for jobs owned by the user
    interviews = db.query(Interview).join(Job).filter(
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).order_by(Interview.interview_date).all()
    result = []
    for interview in interviews:
        result.append({
            "id": interview.id,
            "job_id": interview.job_id,
            "job_title": interview.job.title if interview.job else None,
            "company_name": interview.job.company.name if interview.job and interview.job.company else None,
            "interview_date": interview.interview_date,
            "interview_type": interview.interview_type,
            "interviewer_names": interview.interviewer_names,
            "location": interview.location,
            "notes": interview.notes,
            "outcome": interview.outcome,
            "created_at": interview.created_at
        })
    return result


@router.get("/upcoming")
def get_upcoming_interviews(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    now = datetime.now()
    interviews = db.query(Interview).join(Job).filter(
        Interview.interview_date >= now,
        Interview.outcome == "pending",
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).order_by(Interview.interview_date).all()

    result = []
    for interview in interviews:
        result.append({
            "id": interview.id,
            "job_id": interview.job_id,
            "job_title": interview.job.title if interview.job else None,
            "company_name": interview.job.company.name if interview.job and interview.job.company else None,
            "interview_date": interview.interview_date,
            "interview_type": interview.interview_type,
            "location": interview.location
        })
    return result


@router.get("/job/{job_id}")
def get_interviews_by_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify user has access to this job
    job = db.query(Job).filter(
        Job.id == job_id,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    interviews = db.query(Interview).filter(Interview.job_id == job_id).order_by(Interview.interview_date).all()
    result = []
    for interview in interviews:
        result.append({
            "id": interview.id,
            "interview_date": interview.interview_date,
            "interview_type": interview.interview_type,
            "interviewer_names": interview.interviewer_names,
            "location": interview.location,
            "notes": interview.notes,
            "outcome": interview.outcome
        })
    return result


@router.post("")
def create_interview(
    interview: InterviewCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify user has access to this job
    job = db.query(Job).filter(
        Job.id == interview.job_id,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    db_interview = Interview(**interview.model_dump())
    db.add(db_interview)

    if job.status == "applied":
        job.status = "interviewing"

    # Take ownership of shared job when adding interview
    if job.user_id is None:
        job.user_id = current_user.id

    db.commit()
    db.refresh(db_interview)
    return {"id": db_interview.id, "message": "Interview created successfully"}


@router.put("/{interview_id}")
def update_interview(
    interview_id: int,
    interview: InterviewUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get interview and verify access through job ownership
    db_interview = db.query(Interview).join(Job).filter(
        Interview.id == interview_id,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).first()
    if not db_interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    update_data = interview.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_interview, key, value)

    db.commit()
    db.refresh(db_interview)
    return {"message": "Interview updated successfully"}


@router.delete("/{interview_id}")
def delete_interview(
    interview_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Only allow deleting interviews for user's own jobs
    db_interview = db.query(Interview).join(Job).filter(
        Interview.id == interview_id,
        Job.user_id == current_user.id
    ).first()
    if not db_interview:
        raise HTTPException(status_code=404, detail="Interview not found")

    db.delete(db_interview)
    db.commit()
    return {"message": "Interview deleted successfully"}
