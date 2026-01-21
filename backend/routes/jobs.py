"""
Jobs router with role-aware relevance filtering.

Default behavior:
- Returns ONLY jobs relevant to the current user's role
- Sorted by relevance_score DESC
- Limited to top 50 results

Overrides:
- ?all=true → return all jobs (no relevance filtering)
- ?role=backend → preview relevance for a specific role
- ?min_score=40 → filter by minimum relevance score
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_
from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional, List
import re
import hashlib
from datetime import date, datetime, timedelta

from database import get_db
from models import Job, Company, User, RoleProfile, JobRelevanceScore
from services.relevance_service import (
    compute_job_relevance,
    filter_relevant_jobs,
    RelevanceResult
)
from services.role_profiles_data import get_profile_by_slug, get_all_profiles
from middleware.auth import get_current_user, get_current_user_optional

# Redis caching
try:
    from services.redis_service import redis_service
    REDIS_AVAILABLE = redis_service.ping()
except Exception:
    REDIS_AVAILABLE = False
    redis_service = None

CACHE_TTL_JOBS = 60  # Cache job lists for 60 seconds

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


# ============== Pydantic Models ==============

# Valid job statuses
VALID_JOB_STATUSES = {"wishlist", "applied", "interviewing", "offer", "rejected", "withdrawn"}


class JobCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=500, description="Job title")
    company_id: Optional[int] = Field(None, ge=1)
    location: Optional[str] = Field(None, max_length=255)
    salary_min: Optional[int] = Field(None, ge=0, le=10000000)
    salary_max: Optional[int] = Field(None, ge=0, le=10000000)
    job_url: Optional[str] = Field(None, max_length=2000)
    job_description: Optional[str] = Field(None, max_length=100000)
    status: Optional[str] = Field("wishlist", max_length=50)
    date_found: Optional[date] = None
    date_applied: Optional[date] = None
    excitement_level: Optional[int] = Field(3, ge=1, le=5)

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v and v not in VALID_JOB_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {', '.join(VALID_JOB_STATUSES)}")
        return v

    @field_validator('job_url')
    @classmethod
    def validate_url(cls, v):
        if v:
            # Basic URL format validation
            if not re.match(r'^https?://', v):
                raise ValueError("URL must start with http:// or https://")
        return v


class JobUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    company_id: Optional[int] = Field(None, ge=1)
    location: Optional[str] = Field(None, max_length=255)
    salary_min: Optional[int] = Field(None, ge=0, le=10000000)
    salary_max: Optional[int] = Field(None, ge=0, le=10000000)
    job_url: Optional[str] = Field(None, max_length=2000)
    job_description: Optional[str] = Field(None, max_length=100000)
    status: Optional[str] = Field(None, max_length=50)
    date_found: Optional[date] = None
    date_applied: Optional[date] = None
    excitement_level: Optional[int] = Field(None, ge=1, le=5)

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v and v not in VALID_JOB_STATUSES:
            raise ValueError(f"Invalid status. Must be one of: {', '.join(VALID_JOB_STATUSES)}")
        return v

    @field_validator('job_url')
    @classmethod
    def validate_url(cls, v):
        if v:
            if not re.match(r'^https?://', v):
                raise ValueError("URL must start with http:// or https://")
        return v


class StatusUpdate(BaseModel):
    status: str = Field(..., max_length=50)


class RelevanceInfo(BaseModel):
    """Relevance scoring information for a job."""
    score: float
    is_relevant: bool
    title_matches: List[str] = []
    keyword_matches: List[str] = []
    explanation: str = ""


# ============== Helper Functions ==============

def _get_cache_key(prefix: str, **params) -> str:
    """Generate a cache key from parameters."""
    param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)
    return f"{prefix}:{hashlib.md5(param_str.encode()).hexdigest()[:16]}"


def _cache_get(key: str):
    """Get from cache if Redis available."""
    if REDIS_AVAILABLE and redis_service:
        try:
            return redis_service.cache_get(key)
        except Exception:
            pass
    return None


def _cache_set(key: str, value, ttl: int = CACHE_TTL_JOBS):
    """Set cache if Redis available."""
    if REDIS_AVAILABLE and redis_service:
        try:
            redis_service.cache_set(key, value, ttl)
        except Exception:
            pass


def get_role_profile_for_scoring(
    db: Session,
    role_slug: Optional[str] = None,
    user: Optional[User] = None
) -> Optional[dict]:
    """
    Get role profile for relevance scoring.

    Priority:
    1. Explicit role_slug parameter (for previewing)
    2. User's assigned role profile
    3. Fallback to built-in profile data
    """
    if role_slug:
        # Check database first
        db_profile = db.query(RoleProfile).filter(RoleProfile.slug == role_slug).first()
        if db_profile:
            return {
                "title_patterns": db_profile.title_patterns or {},
                "positive_keywords": db_profile.positive_keywords or {},
                "negative_keywords": db_profile.negative_keywords or [],
                "seniority_config": db_profile.seniority_config or {},
                "relevance_threshold": db_profile.relevance_threshold or 30.0
            }
        # Fallback to built-in data
        return get_profile_by_slug(role_slug)

    if user and user.role_profile:
        return {
            "title_patterns": user.role_profile.title_patterns or {},
            "positive_keywords": user.role_profile.positive_keywords or {},
            "negative_keywords": user.role_profile.negative_keywords or [],
            "seniority_config": user.role_profile.seniority_config or {},
            "relevance_threshold": user.role_profile.relevance_threshold or 30.0
        }

    return None


def job_to_response(job: Job, relevance: Optional[RelevanceResult] = None, include_description: bool = False) -> dict:
    """Convert Job model to response dict with optional relevance info.

    Args:
        job: The Job model instance
        relevance: Optional relevance scoring result
        include_description: If False (default), excludes job_description to reduce response size
    """
    result = {
        "id": job.id,
        "title": job.title,
        "company_id": job.company_id,
        "company_name": job.company.name if job.company else None,
        "location": job.location,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "status": job.status,
        "date_found": job.date_found,
        "date_applied": job.date_applied,
        "excitement_level": job.excitement_level,
        "source": job.source,
        "is_active": job.is_active,
        "created_at": job.created_at,
        "posted_date": job.posted_date,
        "department": job.department,
        "job_url": job.job_url
    }

    # Only include full description if explicitly requested (reduces response size significantly)
    if include_description:
        result["job_description"] = job.job_description

    if relevance:
        result["relevance"] = {
            "score": relevance.relevance_score,
            "is_relevant": relevance.is_relevant,
            "title_matches": relevance.matched_title_patterns[:3],
            "keyword_matches": relevance.matched_keywords[:5],
            "explanation": relevance.explanation
        }

    return result


# ============== Endpoints ==============

@router.get("")
async def get_jobs(
    # Filtering
    status: Optional[str] = Query(None, description="Filter by job status"),
    source: Optional[str] = Query(None, description="Filter by source (greenhouse, lever, etc.)"),
    active_only: bool = Query(True, description="Only show active jobs"),
    company_id: Optional[int] = Query(None, description="Filter by company"),
    posted_within_hours: Optional[int] = Query(None, ge=1, description="Only show jobs posted within this many hours (e.g., 720 = 30 days). If not set, shows all."),

    # Role-aware filtering (THE KEY FEATURE)
    role: Optional[str] = Query(None, description="Role profile slug (devops, backend, frontend, etc.)"),
    all: bool = Query(False, description="Return ALL jobs without relevance filtering"),
    min_score: Optional[float] = Query(None, description="Minimum relevance score (0-100)"),

    # Pagination
    limit: Optional[int] = Query(None, ge=1, description="Maximum results to return (no limit if not specified)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),

    # Auth (optional for public job discovery)
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """
    Get jobs with role-aware relevance filtering.

    DEFAULT BEHAVIOR:
    - Returns only jobs relevant to the current user's role
    - Sorted by relevance score (highest first)
    - Limited to top 50 jobs

    PARAMETERS:
    - role: Override role profile for relevance scoring (e.g., "devops", "backend")
    - all: Set to true to return ALL jobs without relevance filtering
    - min_score: Filter to jobs with at least this relevance score

    EXAMPLE QUERIES:
    - GET /api/jobs → Top 50 relevant jobs for user's role
    - GET /api/jobs?role=devops → Preview relevance for DevOps role
    - GET /api/jobs?all=true → All jobs without filtering
    - GET /api/jobs?min_score=50 → Only highly relevant jobs
    """
    # Generate cache key for this query
    user_role = role or (current_user.role_profile.slug if current_user and current_user.role_profile else None)
    cache_key = _get_cache_key(
        "jobs",
        status=status, source=source, active_only=active_only, company_id=company_id,
        posted_within_hours=posted_within_hours, role=user_role, all_jobs=all,
        min_score=min_score, limit=limit, offset=offset
    )

    # Try cache first
    cached = _cache_get(cache_key)
    if cached:
        return cached

    # Build base query with eager loading for company (avoids N+1)
    query = db.query(Job).options(joinedload(Job.company))

    if status:
        query = query.filter(Job.status == status)
    if source:
        query = query.filter(Job.source == source)
    if active_only:
        query = query.filter(Job.is_active == True)
    if company_id:
        query = query.filter(Job.company_id == company_id)

    # Filter by posted date (only if posted_within_hours is specified)
    if posted_within_hours:
        cutoff_date = datetime.now() - timedelta(hours=posted_within_hours)
        query = query.filter(
            or_(
                Job.posted_date >= cutoff_date,
                (Job.posted_date == None) & (Job.created_at >= cutoff_date)
            )
        )

    # If all=true, return without relevance scoring
    if all:
        total = query.count()
        q = query.order_by(Job.posted_date.desc().nullslast(), Job.created_at.desc()).offset(offset)
        if limit:
            q = q.limit(limit)
        jobs = q.all()
        result = {
            "jobs": [job_to_response(job) for job in jobs],
            "total": total,
            "relevance_filtering": False,
            "role": None
        }
        _cache_set(cache_key, result)
        return result

    # Get role profile for relevance scoring
    role_profile = get_role_profile_for_scoring(db, role, current_user)

    # If no role profile available, fall back to showing all jobs
    if not role_profile:
        total = query.count()
        q = query.order_by(Job.posted_date.desc().nullslast(), Job.created_at.desc()).offset(offset)
        if limit:
            q = q.limit(limit)
        jobs = q.all()
        result = {
            "jobs": [job_to_response(job) for job in jobs],
            "total": total,
            "relevance_filtering": False,
            "role": None,
            "message": "No role profile set. Showing all jobs. Set a role with ?role=devops or configure your user profile."
        }
        _cache_set(cache_key, result)
        return result

    # Get all jobs matching base filters
    all_jobs = query.all()

    # Get user preferences for scoring
    user_prefs = None
    if current_user and current_user.custom_preferences:
        user_prefs = {
            **current_user.custom_preferences,
            "target_seniority": current_user.target_seniority
        }

    # Score and filter jobs
    scored_jobs = []
    for job in all_jobs:
        result = compute_job_relevance(job, role_profile, user_prefs)
        scored_jobs.append((job, result))

    # Sort by relevance score descending
    scored_jobs.sort(key=lambda x: x[1].relevance_score, reverse=True)

    # Apply min_score filter if specified
    if min_score is not None:
        scored_jobs = [(j, r) for j, r in scored_jobs if r.relevance_score >= min_score]
    else:
        # Default: filter to relevant only
        scored_jobs = [(j, r) for j, r in scored_jobs if r.is_relevant]

    # Apply pagination
    total_relevant = len(scored_jobs)
    if limit:
        scored_jobs = scored_jobs[offset:offset + limit]
    elif offset:
        scored_jobs = scored_jobs[offset:]

    # Build response
    role_name = role or (current_user.role_profile.slug if current_user and current_user.role_profile else None)

    response = {
        "jobs": [job_to_response(job, rel) for job, rel in scored_jobs],
        "total": total_relevant,
        "relevance_filtering": True,
        "role": role_name,
        "threshold": role_profile.get("relevance_threshold", 30.0)
    }
    _cache_set(cache_key, response)
    return response


@router.get("/discover")
async def discover_jobs(
    role: str = Query(..., description="Role profile slug (required)"),
    limit: int = Query(25, ge=1, le=100, description="Maximum results"),
    min_score: float = Query(40, ge=0, le=100, description="Minimum relevance score"),
    posted_within_hours: Optional[int] = Query(None, ge=1, description="Only show jobs posted within this many hours (e.g., 720 = 30 days). If not set, shows all."),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Discover highly relevant jobs for a specific role.

    This endpoint is optimized for job seekers who want to see
    only the most relevant opportunities for their role.

    Returns jobs sorted by relevance with detailed scoring breakdown.
    """
    role_profile = get_role_profile_for_scoring(db, role)

    if not role_profile:
        raise HTTPException(
            status_code=400,
            detail=f"Role '{role}' not found. Available roles: devops, backend, frontend, mobile, data, ml, security, fullstack"
        )

    # Get active jobs visible to user (owned or shared)
    query = db.query(Job).filter(
        Job.is_active == True,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    )
    if posted_within_hours:
        cutoff_date = datetime.now() - timedelta(hours=posted_within_hours)
        query = query.filter(
            or_(
                Job.posted_date >= cutoff_date,
                (Job.posted_date == None) & (Job.created_at >= cutoff_date)
            )
        )
    jobs = query.all()

    # Score all jobs
    scored_jobs = []
    for job in jobs:
        result = compute_job_relevance(job, role_profile)
        if result.relevance_score >= min_score:
            scored_jobs.append((job, result))

    # Sort by score
    scored_jobs.sort(key=lambda x: x[1].relevance_score, reverse=True)
    scored_jobs = scored_jobs[:limit]

    return {
        "role": role,
        "role_name": get_profile_by_slug(role).get("name", role) if get_profile_by_slug(role) else role,
        "min_score": min_score,
        "jobs_found": len(scored_jobs),
        "jobs": [
            {
                "id": job.id,
                "title": job.title,
                "company_name": job.company.name if job.company else None,
                "location": job.location,
                "source": job.source,
                "relevance": {
                    "score": rel.relevance_score,
                    "breakdown": rel.score_breakdown,
                    "title_matches": rel.matched_title_patterns,
                    "keywords": rel.matched_keywords[:10],
                    "negative": rel.negative_matches,
                    "explanation": rel.explanation
                }
            }
            for job, rel in scored_jobs
        ]
    }


@router.get("/compare/{job_id}")
async def compare_job_relevance(
    job_id: int,
    roles: str = Query("devops,backend,frontend", description="Comma-separated role slugs to compare"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Compare a job's relevance score across multiple roles.

    Useful for understanding why a job might be relevant for one
    role but not another.

    Example: GET /api/jobs/compare/123?roles=devops,backend,frontend
    """
    job = db.query(Job).filter(
        Job.id == job_id,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    role_list = [r.strip() for r in roles.split(",")]

    comparisons = []
    for role_slug in role_list:
        role_profile = get_role_profile_for_scoring(db, role_slug)
        if not role_profile:
            comparisons.append({
                "role": role_slug,
                "error": f"Role '{role_slug}' not found"
            })
            continue

        result = compute_job_relevance(job, role_profile)
        comparisons.append({
            "role": role_slug,
            "role_name": get_profile_by_slug(role_slug).get("name", role_slug) if get_profile_by_slug(role_slug) else role_slug,
            "relevance_score": result.relevance_score,
            "is_relevant": result.is_relevant,
            "breakdown": result.score_breakdown,
            "title_matches": result.matched_title_patterns,
            "top_keywords": result.matched_keywords[:5],
            "negative_matches": result.negative_matches,
            "explanation": result.explanation
        })

    return {
        "job": {
            "id": job.id,
            "title": job.title,
            "company_name": job.company.name if job.company else None,
            "location": job.location
        },
        "comparisons": comparisons
    }


@router.get("/roles")
def list_available_roles(db: Session = Depends(get_db)):
    """
    List all available role profiles for filtering.

    Returns both built-in profiles and any custom profiles
    stored in the database.
    """
    # Get built-in profiles
    builtin_profiles = get_all_profiles()

    # Get database profiles
    db_profiles = db.query(RoleProfile).filter(RoleProfile.is_active == True).all()

    result = []
    seen_slugs = set()

    # Add database profiles first (they take precedence)
    for profile in db_profiles:
        if profile.slug not in seen_slugs:
            result.append({
                "slug": profile.slug,
                "name": profile.name,
                "description": profile.description,
                "source": "database"
            })
            seen_slugs.add(profile.slug)

    # Add built-in profiles
    for profile in builtin_profiles:
        if profile["slug"] not in seen_slugs:
            result.append({
                "slug": profile["slug"],
                "name": profile["name"],
                "description": profile["description"],
                "source": "builtin"
            })
            seen_slugs.add(profile["slug"])

    return {
        "roles": result,
        "total": len(result)
    }


@router.get("/{job_id}")
async def get_job(
    job_id: int,
    role: Optional[str] = Query(None, description="Role to compute relevance for"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a single job by ID with optional relevance scoring."""
    job = db.query(Job).filter(
        Job.id == job_id,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Compute relevance if role specified
    relevance = None
    if role:
        role_profile = get_role_profile_for_scoring(db, role)
        if role_profile:
            relevance = compute_job_relevance(job, role_profile)

    result = {
        "id": job.id,
        "title": job.title,
        "company_id": job.company_id,
        "company_name": job.company.name if job.company else None,
        "location": job.location,
        "salary_min": job.salary_min,
        "salary_max": job.salary_max,
        "job_url": job.job_url,
        "job_description": job.job_description,
        "status": job.status,
        "date_found": job.date_found,
        "date_applied": job.date_applied,
        "excitement_level": job.excitement_level,
        "source": job.source,
        "external_job_id": job.external_job_id,
        "is_active": job.is_active,
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "posted_date": job.posted_date,
        "department": job.department,
        "interviews": [
            {
                "id": i.id,
                "interview_date": i.interview_date,
                "interview_type": i.interview_type,
                "outcome": i.outcome
            } for i in job.interviews
        ],
        "notes": [
            {
                "id": n.id,
                "content": n.content,
                "note_type": n.note_type,
                "created_at": n.created_at
            } for n in job.notes
        ],
        "documents": [
            {
                "id": d.id,
                "name": d.name,
                "doc_type": d.doc_type
            } for d in job.documents
        ]
    }

    if relevance:
        result["relevance"] = {
            "role": role,
            "score": relevance.relevance_score,
            "is_relevant": relevance.is_relevant,
            "breakdown": relevance.score_breakdown,
            "title_matches": relevance.matched_title_patterns,
            "keyword_matches": relevance.matched_keywords,
            "negative_matches": relevance.negative_matches,
            "explanation": relevance.explanation
        }

    return result


@router.post("")
async def create_job(
    job: JobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new job manually."""
    if job.company_id:
        # Verify user owns this company
        company = db.query(Company).filter(
            Company.id == job.company_id,
            or_(Company.user_id == current_user.id, Company.user_id == None)
        ).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    db_job = Job(**job.model_dump(), source="manual", is_active=True, user_id=current_user.id)
    db.add(db_job)
    db.commit()
    db.refresh(db_job)
    return {"id": db_job.id, "message": "Job created successfully"}


@router.put("/{job_id}")
async def update_job(
    job_id: int,
    job: JobUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing job."""
    db_job = db.query(Job).filter(
        Job.id == job_id,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")

    # If updating company_id, verify user owns the company
    update_data = job.model_dump(exclude_unset=True)
    if "company_id" in update_data and update_data["company_id"]:
        company = db.query(Company).filter(
            Company.id == update_data["company_id"],
            or_(Company.user_id == current_user.id, Company.user_id == None)
        ).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    for key, value in update_data.items():
        setattr(db_job, key, value)

    # Take ownership of shared jobs when updating
    if db_job.user_id is None:
        db_job.user_id = current_user.id

    db.commit()
    db.refresh(db_job)
    return {"message": "Job updated successfully"}


@router.delete("/{job_id}")
async def delete_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a job."""
    # Only allow deleting user's own jobs
    db_job = db.query(Job).filter(
        Job.id == job_id,
        Job.user_id == current_user.id
    ).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")

    db.delete(db_job)
    db.commit()
    return {"message": "Job deleted successfully"}


@router.patch("/{job_id}/status")
async def update_job_status(
    job_id: int,
    status_update: StatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update job application status."""
    db_job = db.query(Job).filter(
        Job.id == job_id,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).first()
    if not db_job:
        raise HTTPException(status_code=404, detail="Job not found")

    valid_statuses = ["wishlist", "applied", "interviewing", "offer", "rejected", "withdrawn"]
    if status_update.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    db_job.status = status_update.status
    if status_update.status == "applied" and not db_job.date_applied:
        db_job.date_applied = date.today()

    # Take ownership of shared jobs when updating status
    if db_job.user_id is None:
        db_job.user_id = current_user.id

    db.commit()
    return {"message": "Status updated successfully"}
