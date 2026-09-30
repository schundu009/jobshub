"""
/api/contracts - contract roles (public read API for cariara.com/jobs/contract).

Public (no auth, cached 120s per param set):
    GET /api/contracts/jobs        (q/loc search, profile matching: roles/skills/seniority/min_match/sort=match)
    GET /api/contracts/jobs/{id}   (fetches a missing description on demand, see contracts.descriptions)
    GET /api/contracts/facets
Admin only:
    GET  /api/contracts/status
    POST /api/contracts/run
"""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import String, case, cast, func, not_, or_
from sqlalchemy.orm import Session, joinedload

from contracts.classifier import CONTRACT_TYPES, TAX_TERMS, VISA_TERMS
from contracts.models import ContractJob
from database import get_db
from services.job_location import country_filter, from_country_codes, normalize_country
from middleware.auth import get_current_admin

try:
    from services.redis_service import redis_service
except Exception:  # pragma: no cover
    redis_service = None

router = APIRouter(prefix="/api/contracts", tags=["contracts"])

CACHE_TTL = 120
DEFAULT_COUNTRY = "US"
MAX_LIMIT = 100
SORTS = ("recent", "rate", "duration", "match")
MATCH_CANDIDATES = 2000  # rows scored in Python per request (most recent first)
SENIORITIES = ("junior", "mid", "senior", "lead", "principal")


# ------------------------------------------------------------------ helpers

_CACHE_VERSION = 3


def _cache_key(prefix: str, **params) -> str:
    raw = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if v is not None)
    # Bump _CACHE_VERSION whenever a response shape changes, so entries written
    # by older code are never served.
    return f"contracts:v{_CACHE_VERSION}:{prefix}:{hashlib.md5(raw.encode()).hexdigest()[:16]}"


def _cache_get(key: str):
    if redis_service is None or not getattr(redis_service, "available", False):
        return None
    try:
        return redis_service.cache_get(key)
    except Exception:
        return None


def _cache_set(key: str, value) -> None:
    if redis_service is None or not getattr(redis_service, "available", False):
        return
    try:
        redis_service.cache_set(key, value, CACHE_TTL)
    except Exception:
        pass


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def plain_text(value: Optional[str], max_chars: Optional[int] = None) -> Optional[str]:
    if not value:
        return value
    text = html.unescape(_TAG_RE.sub(" ", html.unescape(value)))
    text = _WS_RE.sub(" ", text).strip()
    if max_chars and len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text


def _iso_z(dt: Optional[datetime]) -> Optional[str]:
    return dt.replace(microsecond=0).isoformat() + "Z" if dt else None


def _apply_url(url: Optional[str]) -> Optional[str]:
    return url if url and re.match(r"^https?://", url, re.I) else None


def _csv(value: Optional[str], allowed: tuple, name: str, aliases: Optional[dict] = None) -> list[str]:
    if not value:
        return []
    out: list[str] = []
    for token in (t.strip().lower() for t in value.split(",")):
        if not token:
            continue
        if aliases and token in aliases:
            out.extend(aliases[token])
        elif token in allowed:
            out.append(token)
        else:
            raise HTTPException(status_code=400, detail=f"Invalid {name} value '{token}'. Allowed: {', '.join(allowed)}")
    return list(dict.fromkeys(out))


def _json_has(column, code: str):
    """JSON array column contains the code (portable: SQLite JSON text / PostgreSQL json::text)."""
    return cast(column, String).like(f'%"{code}"%')


def _listed_days(dt: Optional[datetime], now: datetime) -> Optional[int]:
    return max(0, (now - dt).days) if dt else None


def contract_to_dict(job: ContractJob, now: datetime, description_chars: Optional[int] = None,
                     full_description: bool = False, match: Optional[tuple] = None) -> dict:
    listed = job.effective_posted_at or job.first_seen_at
    company_name = job.company.name if job.company_id and job.company else None
    out = {
        "id": job.id,
        "title": job.title,
        "company_name": company_name or job.end_client or job.agency_name,
        "agency_name": job.agency_name,
        "end_client": job.end_client,
        "source": job.source,
        "source_type": job.source_type,
        "location": job.location,
        "country_codes": from_country_codes(job.country_codes),
        "employment_type": job.employment_type,
        "tax_terms": job.tax_terms or [],
        "pay_rate_min": job.pay_rate_min,
        "pay_rate_max": job.pay_rate_max,
        "pay_period": job.pay_period,
        "hourly_rate_min": job.hourly_rate_min,
        "hourly_rate_max": job.hourly_rate_max,
        "contract_duration_months": job.contract_duration_months,
        "visa_terms": job.visa_terms or [],
        "skills": job.skills or [],
        "apply_url": _apply_url(job.job_url),
        "job_url": job.job_url,
        "posted_date": _iso_z(job.posted_date),
        "listed_since": _iso_z(listed),
        "listed_days": _listed_days(listed, now),
        "is_active": bool(job.is_active),
        "match_score": match[0] if match else None,
        "match_reasons": match[1] if match else None,
    }
    if full_description:
        out["description"] = job.description
        out["description_text"] = plain_text(job.description)
    elif description_chars:
        out["description"] = plain_text(job.description, description_chars)
    return out


def _viewer_country(country: Optional[str]) -> str:
    """Explicit ?country= wins; these endpoints are public, so otherwise the default (US)."""
    if country:
        if country.strip().upper() in ("ALL", "ANY"):
            return "ALL"
        code = normalize_country(country)
        if not code:
            raise HTTPException(status_code=400, detail=f"Unknown country '{country}' (use ISO-2, e.g. US, GB, IN)")
        return code
    return DEFAULT_COUNTRY


def _base_query(db: Session, country: str, confirmed_only: bool):
    q = db.query(ContractJob).filter(ContractJob.is_active == True)  # noqa: E712
    if country != "ALL":
        q = q.filter(country_filter(ContractJob.country_codes, country, confirmed_only=confirmed_only))
    elif confirmed_only:
        q = q.filter(ContractJob.country_codes.isnot(None), ContractJob.country_codes != "")
    return q


# ------------------------------------------------------------------ search

_TOKEN_SPLIT = re.compile(r"[\s,]+")


def _search_tokens(q: Optional[str]) -> list[str]:
    toks = [t.strip().lower() for t in _TOKEN_SPLIT.split(q or "")]
    return list(dict.fromkeys(t for t in toks if t and len(t) <= 60))[:10]


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _token_filter(haystack, token: str):
    """Case-insensitive match of one search token; short tokens (<= 3 chars: go, qa, ai)
    must stand alone (space / punctuation / JSON quote around them), not be inside a word."""
    tok = _like_escape(token)
    if len(token) > 3:
        return haystack.like(f"%{tok}%", escape="\\")
    padded = " " + haystack + " "
    return or_(*[padded.like(f"%{a}{tok}{b}%", escape="\\")
                 for a in (" ", '"', "/", "(", "-", ".")
                 for b in (" ", '"', "/", ")", "-", ",", ".")])


def _search_haystack(include_description: bool):
    parts = [func.coalesce(ContractJob.title, ""), func.coalesce(cast(ContractJob.skills, String), ""),
             func.coalesce(ContractJob.agency_name, ""), func.coalesce(ContractJob.end_client, "")]
    if include_description:
        parts.append(func.coalesce(ContractJob.description, ""))
    hay = parts[0]
    for p in parts[1:]:
        hay = hay + " " + p
    return func.lower(hay)


def _state_lookup() -> tuple[dict, dict]:
    try:
        from contracts.scrapers._base import US_STATES
    except Exception:  # pragma: no cover
        US_STATES = {}
    by_abbr = {k.upper(): v for k, v in US_STATES.items()}
    by_name = {v.lower(): k.upper() for k, v in US_STATES.items()}
    return by_abbr, by_name


def _location_filter(value: str):
    """Location text OR the state's other spelling: "california" also finds "San Jose, CA", "CA" finds "California"."""
    raw = value.strip()
    low = raw.lower()
    by_abbr, by_name = _state_lookup()
    loc = func.coalesce(ContractJob.location, "")
    conds = [func.lower(loc).like(f"%{_like_escape(low)}%", escape="\\")] if len(raw) > 2 else []
    # word-bounded, case-insensitive view of the location: " SAN JOSE CA 95112 "
    bounded = " " + func.upper(func.replace(func.replace(func.replace(loc, ",", " "), "-", " "), "|", " ")) + " "
    abbr = by_name.get(low) or (raw.upper() if raw.upper() in by_abbr else None)
    if abbr:
        conds.append(bounded.like(f"% {abbr} %"))
        conds.append(func.lower(loc).like(f"%{by_abbr[abbr].lower()}%"))
    elif len(raw) <= 2:
        conds.append(bounded.like(f"% {_like_escape(raw.upper())} %", escape="\\"))
    return or_(*conds)


# ------------------------------------------------------------------ public API

@router.get("/jobs")
def list_contract_jobs(
    employment_type: Optional[str] = Query(None, description="Comma list: contract,contract_to_hire,temporary,freelance (or contract_any)"),
    tax_terms: Optional[str] = Query(None, description="Comma list of w2,c2c,1099 - matches ANY"),
    min_rate: Optional[float] = Query(None, ge=0, le=1000, description="Hourly $; jobs whose top hourly rate >= this"),
    max_rate: Optional[float] = Query(None, ge=0, le=1000, description="Hourly $; jobs whose bottom hourly rate <= this"),
    include_salary_equiv: bool = Query(False, description="Also compare week/month/year pay converted to hourly (year/2080)"),
    min_duration_months: Optional[int] = Query(None, ge=1, le=60),
    visa: Optional[str] = Query(None, description="Comma list of visa_terms codes the job must ALL have"),
    exclude_visa: Optional[str] = Query(None, description="Comma list of visa_terms codes the job must NOT have"),
    country: Optional[str] = Query(None, description="Viewer country, ISO-2 (default US). Unknown-location jobs are included unless confirmed_only"),
    confirmed_only: bool = Query(False, description="Exclude jobs whose location country is unknown"),
    q: Optional[str] = Query(None, max_length=200, description="Search title, skills, agency, client; every word must match"),
    q_description: bool = Query(False, description="Also search the description"),
    location: Optional[str] = Query(None, max_length=100, description="Location text or US state name/abbrev (e.g. 'Austin', 'TX', 'California', 'Remote')"),
    loc: Optional[str] = Query(None, max_length=100, description="Alias of location"),
    roles: Optional[str] = Query(None, max_length=500, description="Comma list of role titles/slugs to match, e.g. 'DevOps Engineer,SRE,platform'"),
    skills: Optional[str] = Query(None, max_length=1000, description="Comma list of candidate skills"),
    seniority: Optional[str] = Query(None, description="junior | mid | senior | lead | principal"),
    min_match: Optional[int] = Query(None, ge=0, le=100, description="Only jobs with match_score >= this (needs roles or skills)"),
    remote: Optional[bool] = Query(None, description="true = remote only"),
    agency: Optional[str] = Query(None, max_length=500, description="Comma list of agency names or source slugs"),
    posted_within_days: Optional[int] = Query(None, ge=1, le=365),
    sort: str = Query("recent", description="recent | rate | duration | match (match needs roles or skills)"),
    limit: int = Query(25, ge=1, le=MAX_LIMIT),
    offset: int = Query(0, ge=0, le=100000),
    description_chars: Optional[int] = Query(None, ge=50, le=5000, description="Include plain-text description truncated to N chars"),
    no_cache: bool = Query(False),
    db: Session = Depends(get_db),
):
    types = _csv(employment_type, CONTRACT_TYPES, "employment_type", {"contract_any": list(CONTRACT_TYPES)})
    taxes = _csv(tax_terms, TAX_TERMS, "tax_terms")
    required_visa = _csv(visa, VISA_TERMS, "visa")
    excluded_visa = _csv(exclude_visa, VISA_TERMS, "exclude_visa")
    if sort not in SORTS:
        raise HTTPException(status_code=400, detail=f"Invalid sort. Allowed: {', '.join(SORTS)}")
    viewer = _viewer_country(country)
    location = location or loc
    if seniority and seniority.strip().lower() not in SENIORITIES + ("jr", "sr", "staff", "entry"):
        raise HTTPException(status_code=400, detail=f"Invalid seniority. Allowed: {', '.join(SENIORITIES)}")
    from contracts.matching import build_profile, max_score_without_skills, max_score_without_title, \
        role_title_phrases, score_job
    profile = build_profile(roles, skills, seniority)
    if (sort == "match" or min_match) and not profile.active:
        raise HTTPException(status_code=400, detail="sort=match and min_match need roles or skills")

    params = dict(q_description=q_description or None, roles=roles, skills=skills,
                  seniority=profile.seniority, min_match=min_match,
                  employment_type=",".join(types) or None, tax_terms=",".join(taxes) or None,
                  min_rate=min_rate, max_rate=max_rate, include_salary_equiv=include_salary_equiv,
                  min_duration_months=min_duration_months, visa=",".join(required_visa) or None,
                  exclude_visa=",".join(excluded_visa) or None, country=viewer, confirmed_only=confirmed_only,
                  q=q, location=location,
                  remote=remote, agency=agency, posted_within_days=posted_within_days, sort=sort,
                  limit=limit, offset=offset, description_chars=description_chars)
    key = _cache_key("jobs", **params)
    if not no_cache:
        cached = _cache_get(key)
        if cached is not None:
            return cached

    query = _base_query(db, viewer, confirmed_only)
    if types:
        query = query.filter(ContractJob.employment_type.in_(types))
    if taxes:
        query = query.filter(or_(*[_json_has(ContractJob.tax_terms, t) for t in taxes]))
    for code in required_visa:
        query = query.filter(_json_has(ContractJob.visa_terms, code))
    for code in excluded_visa:
        query = query.filter(or_(ContractJob.visa_terms.is_(None), not_(_json_has(ContractJob.visa_terms, code))))
    if min_rate is not None or max_rate is not None:
        periods = ["hour", "day"] + (["week", "month", "year"] if include_salary_equiv else [])
        query = query.filter(ContractJob.pay_period.in_(periods))
        if min_rate is not None:
            query = query.filter(ContractJob.hourly_rate_max >= min_rate)
        if max_rate is not None:
            query = query.filter(ContractJob.hourly_rate_min <= max_rate)
    if min_duration_months is not None:
        query = query.filter(ContractJob.contract_duration_months >= min_duration_months)
    tokens = _search_tokens(q)
    if tokens:
        hay = _search_haystack(q_description)
        for tok in tokens:
            query = query.filter(_token_filter(hay, tok))
    if location and location.strip():
        query = query.filter(_location_filter(location))
    if remote is True:
        query = query.filter(func.lower(ContractJob.location).like("%remote%"))
    elif remote is False:
        query = query.filter(or_(ContractJob.location.is_(None), not_(func.lower(ContractJob.location).like("%remote%"))))
    if agency:
        names = [a.strip().lower() for a in agency.split(",") if a.strip()]
        if names:
            query = query.filter(or_(func.lower(ContractJob.agency_name).in_(names),
                                     func.lower(ContractJob.source).in_(names)))
    now = datetime.utcnow()
    if posted_within_days:
        query = query.filter(ContractJob.effective_posted_at >= now - timedelta(days=posted_within_days))

    if profile.active and min_match:
        # Exact SQL pre-filter: below these bounds a job cannot reach min_match.
        if profile.roles and min_match > max_score_without_title(profile):
            phrases = role_title_phrases(profile.roles)
            title_l = " " + func.lower(func.replace(func.replace(ContractJob.title, "-", " "), "/", " ")) + " "
            query = query.filter(or_(*[title_l.like(f"%{_like_escape(p)}%", escape="\\") for p in phrases]))
        elif not profile.roles and min_match > max_score_without_skills(profile):
            hay = func.lower(func.coalesce(ContractJob.title, "") + " " + func.coalesce(cast(ContractJob.skills, String), ""))
            query = query.filter(or_(*[hay.like(f"%{_like_escape(s)}%", escape="\\") for s in profile.skills]))

    if profile.active and (sort == "match" or min_match):
        # Score up to MATCH_CANDIDATES most recent candidates in Python.
        cands = (query.options(joinedload(ContractJob.company))
                 .order_by(ContractJob.effective_posted_at.desc().nullslast(), ContractJob.id.desc())
                 .limit(MATCH_CANDIDATES).all())
        scored = [(r, score_job(r.title, r.skills, profile)) for r in cands]
        if min_match:
            scored = [x for x in scored if x[1][0] >= min_match]
        if sort == "match":
            scored.sort(key=lambda x: -x[1][0])  # stable: recency order breaks ties
        elif sort == "rate":
            scored.sort(key=lambda x: -(x[0].hourly_rate_max or -1))
        elif sort == "duration":
            scored.sort(key=lambda x: -(x[0].contract_duration_months or -1))
        page = scored[offset:offset + limit]
        result = {
            "jobs": [contract_to_dict(r, now, description_chars=description_chars, match=m) for r, m in page],
            "total": len(scored),
            "limit": limit,
            "offset": offset,
            "country": viewer,
            "match_candidates_capped": len(cands) >= MATCH_CANDIDATES,
        }
        _cache_set(key, result)
        return result

    total = query.count()
    if sort == "rate":
        order = [ContractJob.hourly_rate_max.desc().nullslast(), ContractJob.effective_posted_at.desc().nullslast()]
    elif sort == "duration":
        order = [ContractJob.contract_duration_months.desc().nullslast(), ContractJob.effective_posted_at.desc().nullslast()]
    else:
        order = [ContractJob.effective_posted_at.desc().nullslast()]
    rows = (query.options(joinedload(ContractJob.company))
            .order_by(*order, ContractJob.id.desc()).offset(offset).limit(limit).all())
    result = {
        "jobs": [contract_to_dict(r, now, description_chars=description_chars,
                                  match=score_job(r.title, r.skills, profile) if profile.active else None)
                 for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "country": viewer,
    }
    _cache_set(key, result)
    return result


@router.get("/facets")
def contract_facets(
    country: Optional[str] = Query(None, description="Viewer country, ISO-2 (default US)"),
    confirmed_only: bool = Query(False),
    no_cache: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Counts for filter chips over active contract roles visible in ``country``."""
    viewer = _viewer_country(country)
    key = _cache_key("facets", country=viewer, confirmed_only=confirmed_only)
    if not no_cache:
        cached = _cache_get(key)
        if cached is not None:
            return cached
    base = _base_query(db, viewer, confirmed_only)
    total = base.count()
    by_type = {t: 0 for t in CONTRACT_TYPES}
    for et, n in base.with_entities(ContractJob.employment_type, func.count(ContractJob.id)) \
            .group_by(ContractJob.employment_type).all():
        if et in by_type:
            by_type[et] = int(n)

    def combo_counts(column, codes):
        counts = {c: 0 for c in codes}
        for raw, n in base.with_entities(cast(column, String), func.count(ContractJob.id)) \
                .group_by(cast(column, String)).all():
            if not raw:
                continue
            try:
                values = json.loads(raw)
            except Exception:
                continue
            for v in values if isinstance(values, list) else []:
                if v in counts:
                    counts[v] += int(n)
        return counts

    agencies = base.with_entities(ContractJob.agency_name, func.count(ContractJob.id)) \
        .filter(ContractJob.agency_name.isnot(None)) \
        .group_by(ContractJob.agency_name).order_by(func.count(ContractJob.id).desc()).limit(50).all()
    with_rate = base.filter(ContractJob.pay_period.in_(["hour", "day"])).count()
    result = {
        "total": total,
        "country": viewer,
        "confirmed_only": confirmed_only,
        "employment_type": by_type,
        "tax_terms": combo_counts(ContractJob.tax_terms, TAX_TERMS),
        "visa_terms": combo_counts(ContractJob.visa_terms, VISA_TERMS),
        "agencies": [{"name": a, "count": int(n)} for a, n in agencies],
        "with_hourly_rate": with_rate,
    }
    _cache_set(key, result)
    return result


@router.get("/jobs/{job_id}")
def get_contract_job(job_id: int, db: Session = Depends(get_db)):
    key = _cache_key("job", id=job_id)
    cached = _cache_get(key)
    if cached is not None:
        return cached
    job = db.query(ContractJob).options(joinedload(ContractJob.company)).filter(ContractJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Contract job not found")
    from contracts.descriptions import describe
    try:
        status = describe(db, job)
    except Exception:  # never fail the detail view on a fetch problem
        status = "stored" if (job.description or "").strip() else "unavailable"
    result = contract_to_dict(job, datetime.utcnow(), full_description=True)
    result["description_status"] = status
    if status != "unavailable":  # a failed fetch is retried later (descriptions has its own backoff)
        _cache_set(key, result)
    return result


# ------------------------------------------------------------------ admin

@router.get("/status", dependencies=[Depends(get_current_admin)])
def contract_status(db: Session = Depends(get_db)):
    from contracts.service import contract_max_age_days
    from models import ScraperRun

    rows = db.query(
        ContractJob.source, ContractJob.source_type, func.max(ContractJob.agency_name),
        func.count(ContractJob.id),
        func.sum(case((ContractJob.is_active == True, 1), else_=0)),  # noqa: E712
        func.max(ContractJob.last_seen_at),
    ).group_by(ContractJob.source, ContractJob.source_type).all()
    sources = []
    slugs = [r[0] for r in rows]
    last_runs = {}
    if slugs:
        for run in db.query(ScraperRun).filter(ScraperRun.company_slug.in_(slugs)) \
                .order_by(ScraperRun.run_at.desc()).limit(500).all():
            last_runs.setdefault(run.company_slug, run)
    for source, source_type, agency, total, active, last_seen in rows:
        run = last_runs.get(source)
        sources.append({
            "source": source, "source_type": source_type, "agency_name": agency,
            "total": int(total or 0), "active": int(active or 0),
            "last_seen_at": _iso_z(last_seen),
            "last_run_at": _iso_z(run.run_at) if run else None,
            "last_run_success": bool(run.success) if run else None,
            "last_run_note": run.error_message if run else None,
        })
    try:
        from contracts.scrapers import STAFFING_CATEGORY, load_all
        from scrapers.registry import ScraperRegistry
        load_all()
        registered = sorted(ScraperRegistry.get_by_category(STAFFING_CATEGORY))
    except Exception:
        registered = []
    return {
        "contract_max_age_days": contract_max_age_days(db),
        "active_total": sum(s["active"] for s in sources),
        "sources": sorted(sources, key=lambda s: -s["active"]),
        "staffing_scrapers": registered,
    }


@router.post("/run", dependencies=[Depends(get_current_admin)])
def run_contract_scrape(db: Session = Depends(get_db)):
    """Start scrape_all_contracts (inline when APPLY_INLINE_TASKS=1, else on Celery)."""
    from contracts import tasks
    if os.getenv("APPLY_INLINE_TASKS", "").lower() in ("1", "true", "yes"):
        return {"status": "completed", "result": tasks.run_all_contracts_inline(db)}
    try:
        res = tasks.scrape_all_contracts.delay()
        return {"status": "dispatched", "task_id": res.id}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Task queue unavailable: {type(e).__name__}")
