"""
AI-powered features routes with input validation.

Security features:
- JWT authentication required for all endpoints
- Input length limits to prevent abuse
- Rate limiting via main.py middleware
- User-scoped data access
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field, field_validator
from typing import Optional
import re

from database import get_db
from models import Job, Company, User
from services import openai_service
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])

# Maximum text lengths for AI inputs (to control costs and prevent abuse)
MAX_RESUME_LENGTH = 50000  # ~10 pages
MAX_JOB_DESCRIPTION_LENGTH = 50000
MAX_TITLE_LENGTH = 500

# Valid interview types
VALID_INTERVIEW_TYPES = {"phone_screen", "technical", "behavioral", "onsite", "final"}


class CoverLetterRequest(BaseModel):
    job_id: Optional[int] = Field(None, ge=1)
    job_title: Optional[str] = Field(None, max_length=MAX_TITLE_LENGTH)
    company_name: Optional[str] = Field(None, max_length=255)
    job_description: Optional[str] = Field(None, max_length=MAX_JOB_DESCRIPTION_LENGTH)
    resume_text: str = Field(..., min_length=100, max_length=MAX_RESUME_LENGTH)


class InterviewQuestionsRequest(BaseModel):
    job_id: Optional[int] = Field(None, ge=1)
    job_title: Optional[str] = Field(None, max_length=MAX_TITLE_LENGTH)
    job_description: Optional[str] = Field(None, max_length=MAX_JOB_DESCRIPTION_LENGTH)
    interview_type: str = Field("behavioral", max_length=50)

    @field_validator('interview_type')
    @classmethod
    def validate_interview_type(cls, v):
        if v not in VALID_INTERVIEW_TYPES:
            raise ValueError(f"Invalid interview type. Must be one of: {', '.join(VALID_INTERVIEW_TYPES)}")
        return v


class ResumeMatchRequest(BaseModel):
    job_id: Optional[int] = Field(None, ge=1)
    job_description: Optional[str] = Field(None, max_length=MAX_JOB_DESCRIPTION_LENGTH)
    resume_text: str = Field(..., min_length=100, max_length=MAX_RESUME_LENGTH)


class ResumeImprovementRequest(BaseModel):
    resume_text: str = Field(..., min_length=100, max_length=MAX_RESUME_LENGTH)
    job_id: Optional[int] = Field(None, ge=1)
    job_description: Optional[str] = Field(None, max_length=MAX_JOB_DESCRIPTION_LENGTH)


class CompanyResearchRequest(BaseModel):
    company_id: Optional[int] = Field(None, ge=1)
    company_name: Optional[str] = Field(None, max_length=255)
    industry: Optional[str] = Field(None, max_length=100)
    website: Optional[str] = Field(None, max_length=500)

    @field_validator('website')
    @classmethod
    def validate_website(cls, v):
        if v and not re.match(r'^https?://', v):
            raise ValueError("Website must start with http:// or https://")
        return v


@router.post("/cover-letter")
def generate_cover_letter(
    request: CoverLetterRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a tailored cover letter for a job application."""
    job_title = request.job_title
    company_name = request.company_name
    job_description = request.job_description

    if request.job_id:
        job = db.query(Job).filter(Job.id == request.job_id, Job.user_id == current_user.id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job_title = job_title or job.title
        job_description = job_description or job.job_description
        if job.company:
            company_name = company_name or job.company.name

    if not job_title:
        raise HTTPException(status_code=400, detail="Job title is required")
    if not job_description:
        raise HTTPException(status_code=400, detail="Job description is required")
    if not request.resume_text:
        raise HTTPException(status_code=400, detail="Resume text is required")

    try:
        cover_letter = openai_service.generate_cover_letter(
            job_title=job_title,
            company_name=company_name or "the company",
            job_description=job_description,
            resume_text=request.resume_text
        )
        return {"cover_letter": cover_letter}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate cover letter: {str(e)}")


@router.post("/interview-questions")
def generate_interview_questions(
    request: InterviewQuestionsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate practice interview questions for a job."""
    job_title = request.job_title
    job_description = request.job_description

    if request.job_id:
        job = db.query(Job).filter(Job.id == request.job_id, Job.user_id == current_user.id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job_title = job_title or job.title
        job_description = job_description or job.job_description

    if not job_title:
        raise HTTPException(status_code=400, detail="Job title is required")
    if not job_description:
        job_description = f"Position: {job_title}"

    valid_types = ["phone_screen", "technical", "behavioral", "onsite", "final"]
    if request.interview_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Interview type must be one of: {valid_types}")

    try:
        questions = openai_service.generate_interview_questions(
            job_title=job_title,
            job_description=job_description,
            interview_type=request.interview_type
        )
        return {"questions": questions, "interview_type": request.interview_type}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate questions: {str(e)}")


@router.post("/job-match")
def analyze_job_match(
    request: ResumeMatchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Analyze how well a resume matches a job posting."""
    job_description = request.job_description

    if request.job_id:
        job = db.query(Job).filter(Job.id == request.job_id, Job.user_id == current_user.id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job_description = job_description or job.job_description

    if not job_description:
        raise HTTPException(status_code=400, detail="Job description is required")
    if not request.resume_text:
        raise HTTPException(status_code=400, detail="Resume text is required")

    try:
        analysis = openai_service.analyze_resume_job_match(
            job_description=job_description,
            resume_text=request.resume_text
        )
        return analysis
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to analyze match: {str(e)}")


@router.post("/improve-resume")
def get_resume_improvements(
    request: ResumeImprovementRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get suggestions to improve a resume."""
    job_description = request.job_description

    if request.job_id:
        job = db.query(Job).filter(Job.id == request.job_id, Job.user_id == current_user.id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        job_description = job_description or job.job_description

    if not request.resume_text:
        raise HTTPException(status_code=400, detail="Resume text is required")

    try:
        suggestions = openai_service.get_resume_improvements(
            resume_text=request.resume_text,
            target_job_description=job_description
        )
        return {"suggestions": suggestions}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate suggestions: {str(e)}")


@router.post("/company-research")
def research_company(
    request: CompanyResearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Generate a company research summary for interview prep."""
    company_name = request.company_name
    industry = request.industry
    website = request.website

    if request.company_id:
        company = db.query(Company).filter(Company.id == request.company_id, Company.user_id == current_user.id).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")
        company_name = company_name or company.name
        industry = industry or company.industry
        website = website or company.website

    if not company_name:
        raise HTTPException(status_code=400, detail="Company name is required")

    try:
        research = openai_service.generate_company_research(
            company_name=company_name,
            industry=industry,
            website=website
        )
        return {"company_name": company_name, "research": research}
    except ValueError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate research: {str(e)}")
