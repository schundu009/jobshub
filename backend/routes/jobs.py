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

Full-time jobs (cariara.com/jobs):
- q / location / work_type / salary_min+salary_max / company / employment_type are
  applied in SQL and named in the response's applied_filters
- sort=match|recent, skills, seniority, min_match switch scoring to
  services.firm_matching (match_score + match_reasons per job, title and tech stack
  only); the scored list is cached so paging does not re-score
- GET /api/jobs/facets: filter counts
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, and_, func, select, cast, String
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import re
import hashlib
import json
from datetime import date, datetime, timedelta

import html
from collections import defaultdict

from database import get_db
from models import Job, Company, User, RoleProfile
from services.job_location import country_filter, from_country_codes, normalize_country
from services import firm_matching as fm
from services import job_taxonomy as tx

# Contract roles live in contract_jobs and are served by /api/contracts. Direct-hire
# temporary/seasonal roles stay in jobs (employment_type "temporary") and are shown.
CONTRACT_TYPES = ("contract", "contract_to_hire", "freelance")
DEFAULT_COUNTRY = "US"


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
LOCATION_FACET_LIMIT = 400  # most common location strings, for the country / state / city pickers
MAX_RANK_ONLY_CANDIDATES = 50000  # rank_only scores every filtered job (~25k titles take ~0.6s; cached)
CACHE_TTL_JOBS = 300  # Cache job lists for 5 minutes (scoring is expensive)
MIN_ANNUAL_SALARY = 10000  # salary filters ignore pay figures below this (hourly / monthly)


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


def _not_contract():
    """Contract roles live in contract_jobs (/api/contracts); keep strays out of /api/jobs."""
    return or_(Job.employment_type.is_(None), Job.employment_type.notin_(CONTRACT_TYPES))


def _not_evergreen():
    return or_(Job.is_evergreen.is_(None), Job.is_evergreen == False)  # noqa: E712


def _listed_since(job: Job) -> Optional[datetime]:
    """Earlier of the ATS posted date and our first sighting (fallback: created_at)."""
    dates = [d for d in (job.effective_posted_at, job.posted_date, job.first_seen_at) if d is not None]
    if not dates and job.created_at:
        dates = [job.created_at]
    return min(d.replace(tzinfo=None) for d in dates) if dates else None


def freshness_fields(job: Job) -> dict:
    listed = _listed_since(job)
    return {
        "employment_type": job.employment_type,
        "listed_since": listed.replace(microsecond=0).isoformat() + "Z" if listed else None,
        "listed_days": max(0, (datetime.utcnow() - listed).days) if listed else None,
        "country_codes": from_country_codes(job.country_codes),
        "is_evergreen": bool(job.is_evergreen),
        "evergreen_reason": job.evergreen_reason,
    }


def resolve_viewer_country(country: Optional[str], current_user: Optional[User]) -> Optional[str]:
    """
    Which country's jobs to show: explicit ?country= (ALL = no filter) ->
    signed-in user's country_code (admins: no filter) -> US. None = no filter.
    """
    if country:
        if country.strip().upper() in ("ALL", "ANY"):
            return None
        code = normalize_country(country)
        if not code:
            raise HTTPException(status_code=400, detail=f"Unknown country '{country}' (use ISO-2, e.g. US, GB, IN)")
        return code
    if current_user is not None:
        if current_user_is_admin(current_user):
            return None
        code = getattr(current_user, "country_code", None) or normalize_country(getattr(current_user, "country", None))
        if code:
            return code
    return DEFAULT_COUNTRY


def _country_visibility(viewer_country: Optional[str], confirmed_only: bool, current_user: Optional[User]):
    """Jobs in the viewer's country, unknown-location jobs (unless confirmed_only), and the user's own jobs."""
    if viewer_country is None:
        cond = None if not confirmed_only else and_(Job.country_codes.isnot(None), Job.country_codes != "")
    else:
        cond = country_filter(Job.country_codes, viewer_country, confirmed_only=confirmed_only)
    if cond is not None and current_user is not None:
        cond = or_(cond, Job.user_id == current_user.id)
    return cond


def _effective_cutoff_filter(cutoff: datetime):
    """posted_within_hours on the effective (listed-since) date, falling back to created_at."""
    return or_(
        Job.effective_posted_at >= cutoff,
        and_(Job.effective_posted_at.is_(None), func.coalesce(Job.posted_date, Job.created_at) >= cutoff),
    )


def job_to_response(
    job: Job,
    relevance=None,  # RelevanceResult or its response dict
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
        "ai_tech_stack": job.ai_tech_stack,
        "work_type": job.work_type,
        "role_category": job.role_category,
        "seniority": job.seniority,
        "company_domain": job.company.domain if job.company else None,
        **freshness_fields(job),
    }

    # Only include full description if explicitly requested (reduces response size significantly)
    if include_description:
        if description_chars:
            result["job_description"] = plain_text_description(job.job_description, description_chars)
        else:
            result["job_description"] = decode_job_description(job.job_description)

    if relevance:
        result["relevance"] = relevance if isinstance(relevance, dict) else _relevance_dict(relevance)

    return result


def _relevance_dict(relevance: RelevanceResult) -> dict:
    return {
        "score": relevance.relevance_score,
        "is_relevant": relevance.is_relevant,
        "title_matches": relevance.matched_title_patterns[:3],
        "keyword_matches": relevance.matched_keywords[:5],
        "explanation": relevance.explanation
    }


# ============== Endpoints ==============

def _csv(value: Optional[str], limit: int = 50) -> List[str]:
    out: List[str] = []
    for part in (value or "").split(","):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out[:limit]


def _like_pattern(token: str) -> str:
    esc = token.lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def _contains_ci(column, token: str):
    return func.lower(column).like(_like_pattern(token), escape="\\")


def _matches_term(column, token: str, whole_word: bool):
    if whole_word:
        return func.lower(column).regexp_match(fm.word_regex(token))
    return _contains_ci(column, token)


def _company_ids_where(condition):
    return Job.company_id.in_(select(Company.id).where(condition))


def _search_condition(q: str, include_description: bool):
    """Every word of q in title / company / department / location / tech stack (/ description)."""
    per_term = []
    for token, whole in fm.search_terms(q):
        fields = [
            _matches_term(Job.title, token, whole),
            _matches_term(Job.department, token, whole),
            _matches_term(Job.location, token, whole),
            _matches_term(cast(Job.ai_tech_stack, String), token, whole),
            _company_ids_where(_matches_term(Company.name, token, whole)),
        ]
        if include_description:
            fields.append(_matches_term(Job.job_description, token, whole))
        per_term.append(or_(*fields))
    return and_(*per_term) if per_term else None


def _domain_condition(domains: List[str]):
    """Jobs whose company is in one of the domains; "other" also takes unclassified companies."""
    cond = Company.domain.in_(domains)
    if "other" in domains:
        cond = or_(cond, Company.domain.is_(None))
    return _company_ids_where(cond)


def _firm_filter_conditions(
    q: Optional[str], q_description: bool, location: Optional[str], work_type: Optional[str],
    salary_min: Optional[int], salary_max: Optional[int], company: Optional[str], employment_type: Optional[str],
    role_category: Optional[str] = None, seniority: Optional[str] = None, domain: Optional[str] = None,
    countries: Optional[str] = None, visa_ok: bool = False,
) -> dict:
    """SQL condition per applied filter of the jobs page, keyed by filter name (facets leave one out)."""
    conds: dict = {}
    if q and q.strip():
        cond = _search_condition(q, q_description)
        if cond is not None:
            conds["q"] = cond
    places = [p.strip() for p in (location or "").split("|") if p.strip()][:20]
    if places:  # "|"-separated: any of them (metro labels expand to their cities)
        parts = []
        for place in places:
            aliases = fm.resolve_location(place)
            # short tokens ("CA", "NY") as whole words, or "CA" matches Chicago
            parts.extend(_matches_term(Job.location, a, len(a) <= 3) for a in (aliases or [place]))
        conds["location"] = or_(*parts)
    types = [t for t in (x.lower() for x in _csv(work_type)) if t in fm.WORK_TYPES]
    if types:
        conds["work_type"] = Job.work_type.in_(types)
    if salary_min or salary_max:
        lo = func.coalesce(Job.salary_min, Job.salary_max)
        hi = func.coalesce(Job.salary_max, Job.salary_min)
        # a job without pay is out once a salary filter is on; values under 10k are not annual
        parts = [hi.isnot(None), hi >= MIN_ANNUAL_SALARY]
        if salary_min:
            parts.append(hi >= salary_min)
        if salary_max:
            parts.append(lo <= salary_max)
        conds["salary"] = and_(*parts)
    names = [n.lower() for n in _csv(company)]
    if names:
        conds["company"] = _company_ids_where(func.lower(Company.name).in_(names))
    emp = [t for t in (fm.normalize_employment(x) for x in _csv(employment_type)) if t in fm.EMPLOYMENT_ALIASES]
    if emp:
        raw = sorted({v for t in emp for v in fm.EMPLOYMENT_ALIASES[t]})
        cond = Job.employment_type.in_(raw)
        if "full_time" in emp:  # unlabelled postings count as full-time
            cond = or_(cond, Job.employment_type.is_(None), Job.employment_type == "")
        conds["employment_type"] = cond
    cats = [c for c in _csv(role_category) if c in tx.ROLE_CATEGORIES]
    if cats:
        conds["role_category"] = Job.role_category.in_(cats)
    levels = [lv for lv in _csv(seniority) if lv in tx.SENIORITIES]
    if levels:
        conds["seniority"] = Job.seniority.in_(levels)
    domains = [d for d in _csv(domain) if d in tx.DOMAINS]
    if domains:
        conds["domain"] = _domain_condition(domains)
    codes = [c for c in (normalize_country(x) for x in _csv(countries)) if c]
    if codes:
        conds["countries"] = or_(*[country_filter(Job.country_codes, c, confirmed_only=True) for c in codes])
    if visa_ok:
        conds["visa"] = Job.citizenship_restricted.isnot(True)
    return conds


def _base_conditions(
    current_user: Optional[User], *, status=None, source=None, active_only=True, company_id=None,
    include_evergreen=False, viewer_country=None, confirmed_only=False, posted_within_hours=None,
):
    conds = []
    if current_user:
        conds.append(or_(Job.user_id == None, Job.user_id == current_user.id))  # noqa: E711
    else:
        conds.append(Job.user_id == None)  # noqa: E711
    if status:
        conds.append(Job.status == status)
    if source:
        conds.append(Job.source == source)
    if active_only:
        conds.append(Job.is_active == True)  # noqa: E712
    if company_id:
        conds.append(Job.company_id == company_id)
    conds.append(_not_contract())
    if not include_evergreen:
        conds.append(_not_evergreen())
    visibility = _country_visibility(viewer_country, confirmed_only, current_user)
    if visibility is not None:
        conds.append(visibility)
    if posted_within_hours:
        conds.append(_effective_cutoff_filter(datetime.utcnow() - timedelta(hours=posted_within_hours)))
    return conds


LIST_ORDERS = ("salary_high", "salary_low", "company")


def _list_order(sort: Optional[str]):
    if sort == "salary_high":
        return (func.coalesce(Job.salary_max, Job.salary_min).desc().nullslast(), *_recent_order())
    if sort == "salary_low":
        return (func.coalesce(Job.salary_min, Job.salary_max).asc().nullslast(), *_recent_order())
    if sort == "company":
        return (select(Company.name).where(Company.id == Job.company_id).scalar_subquery().asc().nullslast(),
                *_recent_order())
    return _recent_order()


def _recent_order():
    return (Job.effective_posted_at.desc().nullslast(), Job.posted_date.desc().nullslast(),
            Job.created_at.desc(), Job.id.desc())


def _title_prefilter(word_sets):
    """Title contains every word of at least one set (superset of what the matcher scores)."""
    return or_(*[and_(*[_contains_ci(Job.title, w) for w in ws]) for ws in word_sets])


def _skills_prefilter(skills: List[str]):
    spellings = sorted({sp for s in skills for sp in fm.skill_spellings(s)})
    stack = cast(Job.ai_tech_stack, String)
    return or_(*[or_(_contains_ci(Job.title, sp), _contains_ci(stack, sp)) for sp in spellings])


def _stack_list(value) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return [s.strip() for s in value.split(",") if s.strip()]
    if isinstance(value, dict):
        value = [v for vs in value.values() for v in (vs if isinstance(vs, list) else [vs])]
    if isinstance(value, list):
        return [str(v) for v in value if isinstance(v, (str, int, float))]
    return []


def _ranked_get(key: str):
    hit = fm.ttl_cache.get(key)
    if hit is not None:
        return hit
    hit = _cache_get(key)
    if hit is not None:
        fm.ttl_cache.set(key, hit)
    return hit


def _ranked_set(key: str, value) -> None:
    fm.ttl_cache.set(key, value, CACHE_TTL_JOBS)
    _cache_set(key, value, CACHE_TTL_JOBS)


def _page(items: list, offset: int, limit: Optional[int]) -> list:
    return items[offset:offset + limit] if limit else items[offset:]


def _jobs_by_ids(db: Session, ids: List[int]) -> dict:
    if not ids:
        return {}
    rows = db.query(Job).options(joinedload(Job.company)).filter(Job.id.in_(ids)).all()
    return {j.id: j for j in rows}


@router.get("")
def get_jobs(
    # Filtering
    status: Optional[str] = Query(None, description="Filter by job status"),
    source: Optional[str] = Query(None, description="Filter by source (greenhouse, lever, etc.)"),
    active_only: bool = Query(True, description="Only show active jobs"),
    company_id: Optional[int] = Query(None, description="Filter by company"),
    posted_within_hours: Optional[int] = Query(None, ge=1, description="Only show jobs listed within this many hours (e.g., 720 = 30 days), by listed_since (earlier of posted date and first sighting). If not set, shows all."),
    include_evergreen: Optional[bool] = Query(None, description="Include evergreen / long-listed / reposted postings (default: hidden; admins: shown)"),
    country: Optional[str] = Query(None, description="Viewer country ISO-2 (ALL = every country). Default: your profile country, else US; admins: all"),
    confirmed_only: bool = Query(False, description="Exclude jobs whose location country is unknown"),

    # Full-time page filters (named in the response's applied_filters when used)
    q: Optional[str] = Query(None, max_length=200, description="Search: every word must match title, company, department or tech stack (words of 3 letters or fewer match whole words)"),
    q_description: bool = Query(False, description="Also search the job description with q"),
    location: Optional[str] = Query(None, max_length=1000, description="'|'-separated, any of: US metro label or key (e.g. 'San Francisco Bay Area', 'sf') matched by its cities, else a location substring"),
    work_type: Optional[str] = Query(None, description="Comma-separated: remote,hybrid,onsite"),
    salary_min: Optional[int] = Query(None, ge=0, description="Annual USD: keep jobs whose pay range reaches at least this"),
    salary_max: Optional[int] = Query(None, ge=0, description="Annual USD: keep jobs whose pay range starts at or below this"),
    company: Optional[str] = Query(None, max_length=2000, description="Comma-separated company names (case-insensitive exact)"),
    employment_type: Optional[str] = Query(None, description="Comma-separated: full_time,part_time,internship,temporary (unlabelled = full_time)"),
    role_category: Optional[str] = Query(None, max_length=400, description="Comma-separated job_taxonomy.ROLE_CATEGORIES slugs (GET /api/jobs/taxonomy)"),
    seniority_level: Optional[str] = Query(None, max_length=200, description="Comma-separated job_taxonomy.SENIORITIES slugs"),
    domain: Optional[str] = Query(None, max_length=600, description="Comma-separated company domain slugs (job_taxonomy.DOMAINS; other = unclassified too)"),
    countries: Optional[str] = Query(None, max_length=400, description="Comma-separated ISO-2 job countries (known location only); use with country=ALL"),
    visa_ok: bool = Query(False, description="Hide postings that require citizenship / clearance"),

    # Role-aware filtering (THE KEY FEATURE)
    role: Optional[str] = Query(None, description="Single role profile slug (devops, backend, frontend, etc.)"),
    roles: Optional[str] = Query(None, description="Comma-separated role slugs for multi-role filtering (e.g., 'devops,sre,backend')"),
    all: bool = Query(False, description="Return ALL jobs without relevance filtering"),
    min_score: Optional[float] = Query(None, description="Minimum relevance score (0-100); with sort/skills/seniority: minimum match_score"),

    # Skills-based matching (match_score / match_reasons); any of these switches the list to it
    skills: Optional[str] = Query(None, max_length=2000, description="Comma-separated candidate skills"),
    seniority: Optional[str] = Query(None, max_length=40, description="junior | mid | senior | lead | principal"),
    sort: Optional[str] = Query(None, description="match (best match first) | recent (newest first)"),
    min_match: Optional[int] = Query(None, ge=0, le=100, description="Minimum match_score (overrides min_score)"),
    rank_only: bool = Query(False, description="Roles/skills/seniority order the list but do not narrow it: every filtered job is scored, so total equals /facets total"),

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
    Get jobs, matched to roles/skills unless all=true.

    DEFAULT BEHAVIOR:
    - Scored against role/roles (else the signed-in user's role profile), best match first
    - With nothing to match, the newest jobs

    PARAMETERS:
    - role/roles: role slugs to match (e.g., "devops", "backend")
    - all: Set to true to return ALL jobs without matching, newest first
    - min_score: Minimum match_score when min_match is not given
    - no_cache: Bypass cache
    - q, location, work_type, salary_min/salary_max, company, employment_type: server-side filters,
      listed in the response's applied_filters
    - sort=match|recent, skills, seniority, min_match: skills-based matching; each job then carries
      match_score (0-100) and match_reasons

    EXAMPLE QUERIES:
    - GET /api/jobs?all=true&sort=recent&work_type=remote → newest remote jobs
    - GET /api/jobs?roles=backend&skills=go,k8s&sort=match&min_match=60 → strong matches first
    - GET /api/jobs?role=devops → DevOps matches, best first
    """
    if sort is not None:
        sort = sort.strip().lower() or None
        if sort not in (None, "match", "recent", *LIST_ORDERS):
            raise HTTPException(status_code=400, detail="sort must be match, recent, " + ", ".join(LIST_ORDERS))
    viewer_country = resolve_viewer_country(country, current_user)
    if include_evergreen is None:
        include_evergreen = bool(current_user and current_user_is_admin(current_user))

    role_slugs = _csv(roles) if roles else ([role.strip()] if role and role.strip() else [])
    if not role_slugs and not all and current_user and current_user.role_profile:
        role_slugs = [current_user.role_profile.slug]

    filter_by_key = _firm_filter_conditions(
        q, q_description, location, work_type, salary_min, salary_max, company, employment_type,
        role_category, seniority_level, domain, countries, visa_ok)
    filter_conds, applied_filters = list(filter_by_key.values()), list(filter_by_key)

    # Everything that decides which jobs match and how they rank (not the page window)
    selection = dict(
        status=status, source=source, active_only=active_only, company_id=company_id,
        posted_within_hours=posted_within_hours, role=",".join(role_slugs), all_jobs=all,
        include_evergreen=include_evergreen, v="firm3",
        country=viewer_country or "ALL", confirmed_only=confirmed_only, min_score=min_score,
        viewer=current_user.id if current_user else None,
        q=q, q_description=q_description, location=location, work_type=work_type,
        salary_min=salary_min, salary_max=salary_max, company=company, employment_type=employment_type,
        role_category=role_category, seniority_level=seniority_level, domain=domain, countries=countries,
        visa_ok=visa_ok, skills=skills, seniority=seniority, sort=sort, min_match=min_match,
    )
    cache_key = _get_cache_key("jobs", limit=limit, offset=offset, description_chars=description_chars, **selection)
    ranked_key = _get_cache_key("jobs_ranked", **selection)

    # Try cache first (unless no_cache is set)
    if not no_cache:
        cached = _cache_get(cache_key)
        if cached:
            return cached

    conds = _base_conditions(
        current_user, status=status, source=source, active_only=active_only, company_id=company_id,
        include_evergreen=include_evergreen, viewer_country=viewer_country, confirmed_only=confirmed_only,
        posted_within_hours=posted_within_hours,
    ) + filter_conds

    def recent_listing(extra: Optional[dict] = None) -> dict:
        query = db.query(Job).options(joinedload(Job.company)).filter(*conds)
        total = query.count()
        q_ = query.order_by(*_list_order(sort)).offset(offset)
        if limit:
            q_ = q_.limit(limit)
        result = {
            "jobs": [job_to_response(job, include_description=True, description_chars=description_chars) for job in q_.all()],
            "total": total,
            "relevance_filtering": False,
            "role": None,
            "applied_filters": applied_filters,
            **(extra or {}),
        }
        _cache_set(cache_key, result)
        return result

    # If all=true, return without relevance scoring
    if all or sort in LIST_ORDERS:
        return recent_listing({"_api_version": "v2.1_with_descriptions", "sort": sort if sort in LIST_ORDERS else "recent"})

    profile = fm.build_profile(",".join(role_slugs), skills, seniority)
    if not profile.active:
        return recent_listing({"sort": "recent",
                               "message": "No roles or skills to match. Showing the newest jobs."})
    threshold = float(min_match if min_match is not None else (min_score if min_score is not None else 0))
    ranked = None if no_cache else _ranked_get(ranked_key)
    if ranked is None:
        cand = db.query(Job.id, Job.title, Job.ai_tech_stack).filter(*conds)
        if rank_only:
            pass  # the filters decide the set; the profile only orders it
        elif profile.roles:
            cand = cand.filter(_title_prefilter(fm.role_title_word_sets(profile.roles)))
        elif threshold > fm.max_score_without_skills(profile):
            cand = cand.filter(_skills_prefilter(profile.skills))
        try:
            rows = cand.order_by(*_recent_order()).limit(
                MAX_RANK_ONLY_CANDIDATES if rank_only else MAX_SCORING_CANDIDATES).all()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Database query failed: {str(e)}")
        ranked = []
        for job_id, title, stack in rows:
            score, reasons = fm.score_job(title or "", _stack_list(stack), profile)
            if score is not None and score >= threshold:
                ranked.append([job_id, score, reasons or []])
        if sort != "recent":
            ranked.sort(key=lambda r: -r[1])  # stable: newest first among equal scores
        _ranked_set(ranked_key, ranked)
    window = _page(ranked, offset, limit)
    by_id = _jobs_by_ids(db, [r[0] for r in window])
    out = []
    for job_id, score, reasons in window:
        job = by_id.get(job_id)
        if job is None:
            continue
        item = job_to_response(job, include_description=True, description_chars=description_chars)
        item["match_score"] = score
        item["match_reasons"] = reasons
        out.append(item)
    result = {
        "jobs": out,
        "total": len(ranked),
        "relevance_filtering": True,
        "role": ",".join(role_slugs) or None,
        "threshold": threshold,
        "sort": sort or "match",
        "applied_filters": applied_filters,
        "match": {
            "roles": [r.label for r in profile.roles],
            "skills": [profile.skill_labels.get(s, s) for s in profile.skills],
            "seniority": profile.seniority,
        },
    }
    _cache_set(cache_key, result)
    return result


def _options(labels: dict, counts: dict) -> list:
    """Every option of a taxonomy in its order, with its count (0 included)."""
    return [{"value": k, "label": v, "count": int(counts.get(k, 0))} for k, v in labels.items()]


@router.get("/taxonomy")
def job_taxonomy_labels():
    """Slugs and labels of the role, seniority and domain filters, in display order."""
    return {
        "role_categories": [{"value": k, "label": v} for k, v in tx.ROLE_CATEGORIES.items()],
        "seniorities": [{"value": k, "label": v} for k, v in tx.SENIORITIES.items()],
        "domains": [{"value": k, "label": v} for k, v in tx.DOMAINS.items()],
    }


@router.get("/facets")
def job_facets(
    country: Optional[str] = Query(None, description="Viewer country ISO-2 (ALL = every country); default as GET /api/jobs"),
    confirmed_only: bool = Query(False, description="Exclude jobs whose location country is unknown"),
    include_evergreen: Optional[bool] = Query(None, description="Count evergreen / long-listed postings too (default: admins yes)"),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    company_id: Optional[int] = Query(None),
    posted_within_hours: Optional[int] = Query(None, ge=1),
    q: Optional[str] = Query(None, max_length=200),
    q_description: bool = Query(False),
    location: Optional[str] = Query(None, max_length=200),
    work_type: Optional[str] = Query(None),
    salary_min: Optional[int] = Query(None, ge=0),
    salary_max: Optional[int] = Query(None, ge=0),
    company: Optional[str] = Query(None, max_length=2000),
    employment_type: Optional[str] = Query(None),
    role_category: Optional[str] = Query(None, max_length=400),
    seniority_level: Optional[str] = Query(None, max_length=200),
    domain: Optional[str] = Query(None, max_length=600),
    countries: Optional[str] = Query(None, max_length=400),
    visa_ok: bool = Query(False),
    no_cache: bool = Query(False),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """
    Counts for every filter of GET /api/jobs, taking the same parameters (cached 5 minutes).

    Each group is counted with every other applied filter but not its own, so its options show how
    many jobs each would give next to what is already chosen; `total` applies them all and equals the
    list's total.
    """
    viewer_country = resolve_viewer_country(country, current_user)
    if include_evergreen is None:
        include_evergreen = bool(current_user and current_user_is_admin(current_user))
    params = dict(
        country=viewer_country or "ALL", confirmed_only=confirmed_only, include_evergreen=include_evergreen,
        status=status, source=source, company_id=company_id, posted_within_hours=posted_within_hours,
        q=q, q_description=q_description, location=location, work_type=work_type, salary_min=salary_min,
        salary_max=salary_max, company=company, employment_type=employment_type, role_category=role_category,
        seniority_level=seniority_level, domain=domain, countries=countries, visa_ok=visa_ok,
        viewer=current_user.id if current_user else None, v=2,
    )
    key = _get_cache_key("jobs_facets", **params)
    if not no_cache:
        cached = _ranked_get(key)
        if cached is not None:
            return cached
    base = _base_conditions(
        current_user, status=status, source=source, company_id=company_id, include_evergreen=include_evergreen,
        viewer_country=viewer_country, confirmed_only=confirmed_only, posted_within_hours=posted_within_hours)
    filters = _firm_filter_conditions(
        q, q_description, location, work_type, salary_min, salary_max, company, employment_type,
        role_category, seniority_level, domain, countries, visa_ok)

    def where(*leave_out: str) -> list:
        return base + [c for k, c in filters.items() if k not in leave_out]

    def grouped(column, *leave_out: str) -> dict:
        rows = db.query(column, func.count(Job.id)).select_from(Job).filter(*where(*leave_out)).group_by(column).all()
        return {value: int(n) for value, n in rows}

    total = db.query(func.count(Job.id)).filter(*where()).scalar() or 0

    roles = grouped(Job.role_category, "role_category")
    levels = grouped(Job.seniority, "seniority")
    by_domain: dict = defaultdict(int)
    for value, n in (db.query(Company.domain, func.count(Job.id)).select_from(Job)
                     .outerjoin(Company, Job.company_id == Company.id)
                     .filter(*where("domain")).group_by(Company.domain).all()):
        by_domain[value if value in tx.DOMAINS else "other"] += int(n)

    work_types = {t: 0 for t in fm.WORK_TYPES}
    for value, n in grouped(Job.work_type, "work_type").items():
        if value in work_types:
            work_types[value] += n
    employment = {t: 0 for t in fm.EMPLOYMENT_TYPES}
    for value, n in grouped(Job.employment_type, "employment_type").items():
        k = fm.normalize_employment(value)
        employment[k] = employment.get(k, 0) + n

    companies = (
        db.query(Company.name, func.count(Job.id).label("n")).select_from(Job)
        .join(Company, Job.company_id == Company.id)
        .filter(*where("company")).group_by(Company.name)
        .order_by(func.count(Job.id).desc(), Company.name).limit(100).all()
    )
    by_country: dict = defaultdict(int)
    unknown = 0
    for codes, n in grouped(Job.country_codes, "countries").items():
        parsed = from_country_codes(codes)
        if not parsed:
            unknown += n
        for c in parsed:
            by_country[c] += n
    locations = (
        db.query(Job.location, func.count(Job.id)).filter(*where("location"), Job.location.isnot(None), Job.location != "")
        .group_by(Job.location).order_by(func.count(Job.id).desc(), Job.location).limit(LOCATION_FACET_LIMIT).all()
    )
    with_salary = db.query(func.count(Job.id)).filter(
        *where("salary"), or_(Job.salary_min.isnot(None), Job.salary_max.isnot(None))).scalar() or 0
    visa_ok_count = db.query(func.count(Job.id)).filter(
        *where("visa"), Job.citizenship_restricted.isnot(True)).scalar() or 0

    result = {
        "total": int(total),
        "applied_filters": list(filters),
        "role_category": _options(tx.ROLE_CATEGORIES, roles),
        "seniority": _options(tx.SENIORITIES, levels),
        "domain": _options(tx.DOMAINS, by_domain),
        "countries": [{"code": c, "count": n} for c, n in sorted(by_country.items(), key=lambda kv: (-kv[1], kv[0]))],
        "unknown_country": unknown,
        "companies": [{"name": name, "count": int(n)} for name, n in companies if name],
        "locations": [{"name": name, "count": int(n)} for name, n in locations],
        "work_type": work_types,
        "employment_type": employment,
        "with_salary": int(with_salary),
        "visa_ok": int(visa_ok_count),
    }
    _ranked_set(key, result)
    return result


@router.get("/countries")
def job_countries_facet(
    include_evergreen: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Active job counts per country (top 50) for a country picker; unknown-location jobs counted separately."""
    key = _get_cache_key("jobs_countries", include_evergreen=include_evergreen)
    cached = _cache_get(key)
    if cached:
        return cached
    q = db.query(Job.country_codes, func.count(Job.id)).filter(
        Job.is_active == True, Job.user_id == None, _not_contract())  # noqa: E711,E712
    if not include_evergreen:
        q = q.filter(_not_evergreen())
    counts: dict = defaultdict(int)
    unknown = 0
    for codes, n in q.group_by(Job.country_codes).all():
        parsed = from_country_codes(codes)
        if not parsed:
            unknown += int(n)
        for c in parsed:
            counts[c] += int(n)
    top = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:50]
    result = {"countries": [{"code": c, "count": n} for c, n in top], "unknown": unknown}
    _cache_set(key, result)
    return result


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


@router.post("/{job_id}/description")
def fetch_job_description(job_id: int, db: Session = Depends(get_db)):
    """
    The posting's description, fetched now when the feed did not carry it, so
    a job can be read before applying (the 30-minute backfill would get to it
    later). Shared jobs only; at most one fetch per job a minute.
    """
    from services import job_descriptions
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == None).first()  # noqa: E711
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    try:
        outcome, _ = job_descriptions.fetch_description(db, job, on_demand=True)
    except Exception:
        db.rollback()
        outcome = "failed"
    # A short text (a list summary the posting could not improve on) is still
    # better than nothing to read.
    text = (job.job_description or "").strip()
    readable = bool(text) and text != "No description available."
    return {
        "job_description": decode_job_description(job.job_description) if readable else "",
        "description_status": "closed" if outcome == "closed" else ("stored" if readable else "unavailable"),
    }


@router.get("/{job_id}")
def get_job(
    job_id: int,
    role: Optional[str] = Query(None, description="Role to compute relevance for"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db)
):
    """Get a single job by ID with optional relevance scoring.

    Public for shared jobs (user_id NULL); a private job only for its owner.
    """
    visible = (or_(Job.user_id == current_user.id, Job.user_id == None) if current_user  # noqa: E711
               else Job.user_id == None)  # noqa: E711
    job = db.query(Job).filter(Job.id == job_id, visible).first()
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
        "work_type": job.work_type,
        **freshness_fields(job),
        "reposted_count": job.reposted_count or 0,
        "first_seen_at": job.first_seen_at,
        "last_seen_at": job.last_seen_at,
        "interviews": [
            {
                "id": i.id,
                "interview_date": i.interview_date,
                "interview_type": i.interview_type,
                "outcome": i.outcome
            } for i in (job.interviews if current_user is not None else [])
        ],
        "notes": [
            {
                "id": n.id,
                "content": n.content,
                "note_type": n.note_type,
                "created_at": n.created_at
            } for n in (job.notes if current_user is not None else [])
        ],
        "documents": [
            {
                "id": d.id,
                "name": d.name,
                "doc_type": d.doc_type
            } for d in job.documents if current_user is not None and d.user_id == current_user.id
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

    now = datetime.utcnow()
    db_job = Job(**job.model_dump(), source="manual", is_active=True, user_id=current_user.id,
                 first_seen_at=now, last_seen_at=now, effective_posted_at=now)
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


