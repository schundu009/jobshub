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
from sqlalchemy import or_, and_, not_, func
from pydantic import BaseModel, Field, HttpUrl, field_validator
from typing import Optional, List
import re
import hashlib
import json
from datetime import date, datetime, timedelta

import html
import time
from collections import defaultdict, deque

from database import get_db
from models import Job, Company, User, RoleProfile, JobRelevanceScore


def decode_job_description(description: str) -> str:
    """Decode HTML entities in job descriptions."""
    if not description:
        return description
    # Decode HTML entities (e.g., &lt; -> <, &gt; -> >, &amp; -> &)
    decoded = html.unescape(description)
    # Check if still encoded (double-encoding) and decode again
    if '&lt;' in decoded or '&gt;' in decoded or '&amp;' in decoded:
        decoded = html.unescape(decoded)
    return decoded
from services.relevance_service import (
    compute_job_relevance,
    filter_relevant_jobs,
    RelevanceResult
)
from services.role_profiles_data import get_profile_by_slug, get_all_profiles
from middleware.auth import get_current_user, get_current_user_optional, is_admin as current_user_is_admin

# Redis caching
try:
    from services.redis_service import redis_service
except Exception:
    redis_service = None

MAX_SCORING_CANDIDATES = 3000  # most recent title-matched jobs scored per request
CACHE_TTL_JOBS = 300  # Cache job lists for 5 minutes (scoring is expensive)


def _apply_title_filter(query, role_profiles: List[dict]):
    """
    Apply database-level title filtering based on role profile patterns.

    This dramatically reduces the number of jobs to score by filtering
    at the SQL level using ILIKE patterns.
    """
    if not role_profiles:
        return query

    # Collect all patterns from all role profiles
    include_patterns = []
    exclude_patterns = []

    for profile in role_profiles:
        title_config = profile.get("title_patterns", {})
        # Include strong and weak match patterns
        include_patterns.extend(title_config.get("strong_match", []))
        include_patterns.extend(title_config.get("weak_match", []))
        # Collect exclude patterns
        exclude_patterns.extend(title_config.get("exclude", []))

    # Build SQL ILIKE conditions for inclusion
    include_conditions = []
    for pattern in include_patterns:
        # Convert to SQL ILIKE pattern (case-insensitive, partial match)
        include_conditions.append(func.lower(Job.title).contains(pattern.lower()))

    # Build SQL NOT ILIKE conditions for exclusion
    exclude_conditions = []
    for pattern in exclude_patterns:
        exclude_conditions.append(func.lower(Job.title).contains(pattern.lower()))

    # Apply filters: must match at least one include pattern, and not match any exclude pattern
    if include_conditions:
        query = query.filter(or_(*include_conditions))

    if exclude_conditions:
        query = query.filter(not_(or_(*exclude_conditions)))

    return query


def _redis_available() -> bool:
    """Whether to attempt Redis at all.

    No PING round-trip per call: cache operations fail open on their own and
    the Redis service trips a short circuit breaker on connection errors.
    """
    return redis_service is not None and redis_service.available

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
    if _redis_available():
        try:
            return redis_service.cache_get(key)
        except Exception:
            pass
    return None


def _serialize_for_cache(obj):
    """Convert datetime objects for JSON serialization."""
    import json
    from datetime import datetime, date

    def default_serializer(o):
        if isinstance(o, datetime):
            return o.isoformat()
        elif isinstance(o, date):
            return o.isoformat()
        raise TypeError(f"Object of type {type(o)} is not JSON serializable")

    return json.loads(json.dumps(obj, default=default_serializer))


def _cache_set(key: str, value, ttl: int = CACHE_TTL_JOBS):
    """Set cache if Redis available."""
    if _redis_available():
        try:
            # Serialize datetime objects before caching
            serializable = _serialize_for_cache(value)
            redis_service.cache_set(key, serializable, ttl)
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


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def plain_text_description(description: Optional[str], max_chars: Optional[int] = None) -> Optional[str]:
    """Strip HTML tags, decode entities, collapse whitespace and optionally truncate."""
    if not description:
        return description
    text = decode_job_description(description)
    text = _TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = _WS_RE.sub(" ", text).strip()
    if max_chars and len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "\u2026"
    return text


def job_to_response(
    job: Job,
    relevance: Optional[RelevanceResult] = None,
    include_description: bool = False,
    description_chars: Optional[int] = None,
) -> dict:
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
        "job_url": job.job_url,
        "ai_summary": job.ai_summary,
        "ai_tech_stack": job.ai_tech_stack
    }

    # Only include full description if explicitly requested (reduces response size significantly)
    if include_description:
        if description_chars:
            result["job_description"] = plain_text_description(job.job_description, description_chars)
        else:
            result["job_description"] = decode_job_description(job.job_description)

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
def get_jobs(
    # Filtering
    status: Optional[str] = Query(None, description="Filter by job status"),
    source: Optional[str] = Query(None, description="Filter by source (greenhouse, lever, etc.)"),
    active_only: bool = Query(True, description="Only show active jobs"),
    company_id: Optional[int] = Query(None, description="Filter by company"),
    posted_within_hours: Optional[int] = Query(None, ge=1, description="Only show jobs posted within this many hours (e.g., 720 = 30 days). If not set, shows all."),

    # Role-aware filtering (THE KEY FEATURE)
    role: Optional[str] = Query(None, description="Single role profile slug (devops, backend, frontend, etc.)"),
    roles: Optional[str] = Query(None, description="Comma-separated role slugs for multi-role filtering (e.g., 'devops,sre,backend')"),
    all: bool = Query(False, description="Return ALL jobs without relevance filtering"),
    min_score: Optional[float] = Query(None, description="Minimum relevance score (0-100)"),

    # Pagination
    limit: Optional[int] = Query(None, ge=1, description="Maximum results to return (no limit if not specified)"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),

    # Cache control
    no_cache: bool = Query(False, description="Bypass cache and get fresh data"),

    # Payload size control
    description_chars: Optional[int] = Query(
        None, ge=100, le=20000,
        description="If set, job_description is returned as plain text truncated to this many characters"
    ),

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
    - no_cache: Bypass Redis cache

    EXAMPLE QUERIES:
    - GET /api/jobs → Top 50 relevant jobs for user's role
    - GET /api/jobs?role=devops → Preview relevance for DevOps role
    - GET /api/jobs?all=true → All jobs without filtering
    - GET /api/jobs?min_score=50 → Only highly relevant jobs
    """
    # Generate cache key for this query
    user_role = roles or role or (current_user.role_profile.slug if current_user and current_user.role_profile else None)
    score_preferences = None
    if current_user and not all:
        score_preferences = hashlib.sha256(json.dumps({
            "user_id": current_user.id,
            "custom_preferences": current_user.custom_preferences or {},
            "target_seniority": current_user.target_seniority,
        }, sort_keys=True, default=str).encode()).hexdigest()[:16]
    cache_key = _get_cache_key(
        "jobs",
        status=status, source=source, active_only=active_only, company_id=company_id,
        posted_within_hours=posted_within_hours, role=user_role, all_jobs=all,
        score_preferences=score_preferences,
        min_score=min_score, limit=limit, offset=offset,
        viewer=current_user.id if current_user else None,
        description_chars=description_chars,
    )

    # Try cache first (unless no_cache is set)
    if not no_cache:
        cached = _cache_get(cache_key)
        if cached:
            return cached

    # Build base query with eager loading for company (avoids N+1)
    query = db.query(Job).options(joinedload(Job.company))

    # Visibility: shared jobs (user_id IS NULL) plus the current user's own private jobs
    if current_user:
        query = query.filter(or_(Job.user_id == None, Job.user_id == current_user.id))
    else:
        query = query.filter(Job.user_id == None)

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
            "jobs": [job_to_response(job, include_description=True, description_chars=description_chars) for job in jobs],
            "total": total,
            "relevance_filtering": False,
            "role": None,
            "_api_version": "v2.1_with_descriptions"
        }
        _cache_set(cache_key, result)
        return result

    # Handle multiple roles (comma-separated) or single role
    role_slugs = []
    if roles:
        role_slugs = [r.strip() for r in roles.split(',') if r.strip()]
    elif role:
        role_slugs = [role]

    # Get role profiles for all specified roles
    role_profiles = []
    for slug in role_slugs:
        profile = get_role_profile_for_scoring(db, slug, None)  # Get by slug, not user
        if profile:
            role_profiles.append(profile)

    # If no roles specified, try user's role profile
    if not role_profiles and current_user and current_user.role_profile:
        profile = get_role_profile_for_scoring(db, None, current_user)
        if profile:
            role_profiles.append(profile)

    # If no role profile available, fall back to showing all jobs
    if not role_profiles:
        total = query.count()
        q = query.order_by(Job.posted_date.desc().nullslast(), Job.created_at.desc()).offset(offset)
        if limit:
            q = q.limit(limit)
        jobs = q.all()
        result = {
            "jobs": [job_to_response(job, include_description=True, description_chars=description_chars) for job in jobs],
            "total": total,
            "relevance_filtering": False,
            "role": None,
            "message": "No role profile set. Showing all jobs. Set a role with ?role=devops or ?roles=devops,sre"
        }
        _cache_set(cache_key, result)
        return result

    # Apply database-level title filtering based on role patterns
    # This dramatically reduces the number of jobs to score
    query = _apply_title_filter(query, role_profiles)

    # After title filtering, score only the most recent candidates. Scoring
    # needs title + description, so descriptions are loaded, but capping the
    # candidate set bounds memory/latency on broad role filters.
    try:
        all_jobs = query.order_by(
            Job.posted_date.desc().nullslast(),
            Job.created_at.desc()
        ).limit(MAX_SCORING_CANDIDATES).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")

    # Get user preferences for scoring
    user_prefs = None
    if current_user and current_user.custom_preferences:
        user_prefs = {
            **current_user.custom_preferences,
            "target_seniority": current_user.target_seniority
        }

    # Get threshold - use min_score if provided, otherwise default to 70 for quality filtering
    effective_min_score = min_score if min_score is not None else 70.0
    threshold = effective_min_score

    # Score and filter jobs - use BEST score across all selected roles
    scored_jobs = []
    try:
        for job in all_jobs:
            best_result = None
            best_score = -1
            # Score against each role profile and keep the best
            for role_profile in role_profiles:
                result = compute_job_relevance(job, role_profile, user_prefs)
                if result.relevance_score > best_score:
                    best_score = result.relevance_score
                    best_result = result

            if best_result and best_result.relevance_score >= effective_min_score:
                scored_jobs.append((job, best_result))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Relevance scoring failed: {str(e)}")

    # Sort by relevance score descending
    scored_jobs.sort(key=lambda x: x[1].relevance_score, reverse=True)

    # Apply pagination
    total_relevant = len(scored_jobs)
    if limit:
        scored_jobs = scored_jobs[offset:offset + limit]
    elif offset:
        scored_jobs = scored_jobs[offset:]

    # Build response
    role_name = roles or role or (current_user.role_profile.slug if current_user and current_user.role_profile else None)

    response = {
        "jobs": [job_to_response(job, rel, include_description=True, description_chars=description_chars) for job, rel in scored_jobs],
        "total": total_relevant,
        "relevance_filtering": True,
        "role": role_name,
        "threshold": threshold
    }
    _cache_set(cache_key, response)
    return response


@router.get("/discover")
def discover_jobs(
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
    query = db.query(Job).options(joinedload(Job.company)).filter(
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
    # Same candidate selection as GET /api/jobs: SQL title pre-filter, then
    # only the most recent MAX_SCORING_CANDIDATES get scored (was: every active job).
    query = _apply_title_filter(query, [role_profile])
    jobs = query.order_by(
        Job.posted_date.desc().nullslast(),
        Job.created_at.desc()
    ).limit(MAX_SCORING_CANDIDATES).all()

    # Score candidate jobs
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
def compare_job_relevance(
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
def get_job(
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
        "job_description": decode_job_description(job.job_description),
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
        "ai_summary": job.ai_summary,
        "ai_tech_stack": job.ai_tech_stack,
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
            } for d in job.documents if d.user_id == current_user.id
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
def create_job(
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


def _editable_job(db: Session, job_id: int, user: User) -> Job:
    """
    Admins may edit/delete any job; other users only their own.
    Shared rows (user_id NULL) are admin-only (403), others' rows are 404.
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if current_user_is_admin(user) or job.user_id == user.id:
        return job
    if job.user_id is None:
        raise HTTPException(status_code=403, detail="Only admins can modify shared jobs")
    raise HTTPException(status_code=404, detail="Job not found")


@router.put("/{job_id}")
def update_job(
    job_id: int,
    job: JobUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing job. Shared (scraped) jobs are admin-only."""
    db_job = _editable_job(db, job_id, current_user)

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

    db.commit()
    db.refresh(db_job)
    return {"message": "Job updated successfully"}


@router.delete("/{job_id}")
def delete_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a job. Users delete their own jobs; admins any job."""
    db_job = _editable_job(db, job_id, current_user)

    db.delete(db_job)
    db.commit()
    return {"message": "Job deleted successfully"}


@router.patch("/{job_id}/status")
def update_job_status(
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


# Simple in-memory per-user rate limit for AI summary generation
AI_SUMMARY_RATE_LIMIT = 60          # requests
AI_SUMMARY_RATE_WINDOW = 3600       # seconds
_ai_summary_calls: dict = defaultdict(deque)
_ADMIN_ROLES = {"admin", "administrator", "manager", "developer"}


def _check_ai_summary_rate_limit(user_id: int) -> None:
    now = time.monotonic()
    calls = _ai_summary_calls[user_id]
    while calls and now - calls[0] > AI_SUMMARY_RATE_WINDOW:
        calls.popleft()
    if len(calls) >= AI_SUMMARY_RATE_LIMIT:
        retry_after = int(AI_SUMMARY_RATE_WINDOW - (now - calls[0])) + 1
        raise HTTPException(
            status_code=429,
            detail="Too many AI summary requests. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )
    calls.append(now)


@router.post("/{job_id}/ai-summary")
def generate_job_ai_summary(
    job_id: int,
    force: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Generate an AI summary of the job description.
    Returns cached summary if available, otherwise generates and stores it.
    force=true (regenerate even if cached) is honoured for admins only.
    """
    job = db.query(Job).filter(
        Job.id == job_id,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if force and current_user.role not in _ADMIN_ROLES:
        force = False

    # Return cached summary if available and not forcing regeneration
    if not force and job.ai_summary and job.ai_tech_stack:
        return {
            "summary": job.ai_summary,
            "tech_stack": job.ai_tech_stack,
            "cached": True
        }

    # Generate new summary
    if not job.job_description:
        return {
            "summary": "",
            "tech_stack": [],
            "cached": False,
            "error": "No job description available"
        }

    _check_ai_summary_rate_limit(current_user.id)

    try:
        from services.ai_service import summarize_job_description
        result = summarize_job_description(job.title, job.job_description)

        # Cache the result
        job.ai_summary = result.get("summary", "")
        job.ai_tech_stack = result.get("tech_tools", [])
        db.commit()

        return {
            "summary": job.ai_summary,
            "tech_stack": job.ai_tech_stack,
            "cached": False
        }
    except Exception as e:
        return {
            "summary": "",
            "tech_stack": [],
            "cached": False,
            "error": str(e)
        }


@router.get("/{job_id}/ai-summary")
def get_job_ai_summary(
    job_id: int,
    db: Session = Depends(get_db)
):
    """
    Get the AI summary for a job (returns empty if not generated yet).
    """
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    return {
        "summary": job.ai_summary or "",
        "tech_stack": job.ai_tech_stack or [],
        "has_summary": bool(job.ai_summary)
    }
