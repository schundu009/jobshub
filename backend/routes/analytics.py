from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, true, text, case, and_
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from database import get_db
from models import Job, Company, Contact, Interview, Note, Document, User
from middleware.auth import get_current_user
from services.redis_service import redis_service
from config import settings

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


STATUSES = ["wishlist", "applied", "interviewing", "offer", "rejected", "withdrawn"]
ANALYTICS_CACHE_PREFIX = "analytics:"


def _cached(name: str, compute):
    """Return cached analytics payload or compute + cache it (fails open)."""
    key = f"{ANALYTICS_CACHE_PREFIX}{name}"
    cached = redis_service.cache_get(key)
    if cached is not None:
        return cached
    value = jsonable_encoder(compute())
    redis_service.cache_set(key, value, settings.cache_ttl_analytics)
    return value


def _count_if(condition):
    return func.coalesce(func.sum(case((condition, 1), else_=0)), 0)


@router.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    """Get dashboard summary statistics."""
    def compute():
        # One pass over jobs for all active/status counts
        row = db.query(
            _count_if(Job.is_active == True),  # noqa: E712
            *[_count_if(and_(Job.status == st, Job.is_active == True)) for st in STATUSES],  # noqa: E712
        ).one()
        total_jobs = int(row[0])
        status_counts = {st: int(row[i + 1]) for i, st in enumerate(STATUSES)}

        total_companies = db.query(func.count(Company.id)).scalar() or 0
        total_contacts = db.query(func.count(Contact.id)).scalar() or 0

        now = datetime.now()
        week_later = now + timedelta(days=7)

        upcoming_interviews = db.query(func.count(Interview.id)).join(Job).filter(
            Interview.interview_date >= now,
            Interview.interview_date <= week_later,
            Interview.outcome == "pending"
        ).scalar() or 0

        recent_jobs = db.query(
            Job.id, Job.title, Job.status, Job.created_at, Company.name
        ).outerjoin(Company, Job.company_id == Company.id).order_by(
            Job.created_at.desc()
        ).limit(5).all()

        recent_activity = [
            {
                "id": j_id,
                "title": title,
                "company_name": company_name,
                "status": status,
                "created_at": created_at
            } for j_id, title, status, created_at, company_name in recent_jobs
        ]

        return {
            "total_jobs": total_jobs,
            "total_companies": total_companies,
            "total_contacts": total_contacts,
            "status_counts": status_counts,
            "upcoming_interviews": upcoming_interviews,
            "recent_activity": recent_activity
        }

    return _cached("summary", compute)


@router.get("/status-breakdown")
def get_status_breakdown(db: Session = Depends(get_db)):
    """Get detailed breakdown of jobs by status."""
    def compute():
        counts = dict(db.query(Job.status, func.count(Job.id)).group_by(Job.status).all())
        total = sum(counts.values())
        breakdown = []
        for status in STATUSES:
            count = counts.get(status, 0)
            percentage = round((count / total * 100), 1) if total > 0 else 0
            breakdown.append({
                "status": status,
                "count": count,
                "percentage": percentage
            })
        return {
            "total": total,
            "breakdown": breakdown
        }

    return _cached("status-breakdown", compute)


@router.get("/timeline")
def get_timeline(db: Session = Depends(get_db)):
    """Get applications over time (last 30 days)."""
    def compute():
        now = datetime.now()
        thirty_days_ago = now - timedelta(days=30)

        # func.date() works on both PostgreSQL (returns date) and SQLite (returns 'YYYY-MM-DD')
        day = func.date(Job.created_at)
        rows = db.query(day, func.count(Job.id)).filter(
            Job.created_at >= thirty_days_ago
        ).group_by(day).all()

        daily_counts = defaultdict(int)
        for d, count in rows:
            if d is None:
                continue
            date_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)[:10]
            daily_counts[date_str] += count

        # Fill in missing dates
        timeline = []
        current = thirty_days_ago
        while current <= now:
            date_str = current.strftime("%Y-%m-%d")
            timeline.append({
                "date": date_str,
                "count": daily_counts.get(date_str, 0)
            })
            current += timedelta(days=1)

        return {"timeline": timeline}

    return _cached("timeline", compute)


@router.get("/response-rate")
def get_response_rate(db: Session = Depends(get_db)):
    """Calculate response rate and success metrics."""
    def compute():
        row = db.query(
            _count_if(Job.status != "wishlist"),
            _count_if(Job.status.in_(["interviewing", "offer"])),
            _count_if(Job.status == "offer"),
            _count_if(Job.status == "rejected"),
        ).one()
        total_applied, got_interview, got_offer, rejected = (int(v) for v in row)

        interview_rate = round((got_interview / total_applied * 100), 1) if total_applied > 0 else 0
        offer_rate = round((got_offer / total_applied * 100), 1) if total_applied > 0 else 0
        rejection_rate = round((rejected / total_applied * 100), 1) if total_applied > 0 else 0

        return {
            "total_applied": total_applied,
            "got_interview": got_interview,
            "got_offer": got_offer,
            "rejected": rejected,
            "interview_rate": interview_rate,
            "offer_rate": offer_rate,
            "rejection_rate": rejection_rate
        }

    return _cached("response-rate", compute)


@router.get("/by-company")
def get_jobs_by_company(db: Session = Depends(get_db)):
    """Get job applications grouped by company."""
    def compute():
        rows = db.query(
            Company.id, Company.name, Job.status, func.count(Job.id)
        ).join(Job, Job.company_id == Company.id).group_by(
            Company.id, Company.name, Job.status
        ).order_by(Company.id).all()

        by_company = {}
        for company_id, company_name, status, count in rows:
            entry = by_company.setdefault(company_id, {
                "company_id": company_id,
                "company_name": company_name,
                "job_count": 0,
                "status_breakdown": {}
            })
            entry["job_count"] += count
            entry["status_breakdown"][status] = entry["status_breakdown"].get(status, 0) + count

        result = list(by_company.values())
        # Sort by job count descending
        result.sort(key=lambda x: x["job_count"], reverse=True)
        return {"companies": result}

    return _cached("by-company", compute)


@router.get("/by-location")
def get_jobs_by_location(db: Session = Depends(get_db)):
    """Get job applications grouped by location."""
    def compute():
        rows = db.query(Job.location, func.count(Job.id)).group_by(Job.location).all()

        location_counts = defaultdict(int)
        for location, count in rows:
            location_counts[location or "Not specified"] += count

        result = [
            {"location": loc, "count": count}
            for loc, count in sorted(location_counts.items(), key=lambda x: x[1], reverse=True)
        ]
        return {"locations": result}

    return _cached("by-location", compute)


@router.get("/excitement-distribution")
def get_excitement_distribution(db: Session = Depends(get_db)):
    """Get distribution of excitement levels."""
    def compute():
        counts = dict(
            db.query(Job.excitement_level, func.count(Job.id)).filter(
                Job.excitement_level.between(1, 5)
            ).group_by(Job.excitement_level).all()
        )
        distribution = [{"level": level, "count": counts.get(level, 0)} for level in range(1, 6)]

        avg_excitement = db.query(func.avg(Job.excitement_level)).scalar()
        avg_excitement = round(float(avg_excitement), 2) if avg_excitement else 0

        return {
            "distribution": distribution,
            "average": avg_excitement
        }

    return _cached("excitement-distribution", compute)


@router.get("/by-job-type")
def get_jobs_by_type(db: Session = Depends(get_db)):
    """Get job counts grouped by job type (derived from title keywords)."""
    import re

    # Job type patterns - order matters (more specific first)
    JOB_TYPE_PATTERNS = {
        'fullstack': [r'full\s*stack', r'fullstack'],
        'frontend': [r'front\s*end', r'frontend', r'\bui\b', r'\bux\b', r'react', r'angular', r'vue'],
        'backend': [r'back\s*end', r'backend', r'server', r'\bapi\b', r'java\b', r'python', r'golang', r'node'],
        'devops': [r'devops', r'\bsre\b', r'site reliability', r'platform', r'infrastructure', r'cloud'],
        'data': [r'\bdata\b', r'analytics', r'\bml\b', r'machine learning', r'\bai\b', r'artificial intelligence', r'scientist'],
        'mobile': [r'mobile', r'\bios\b', r'android', r'swift', r'kotlin'],
        'security': [r'security', r'infosec', r'cyber'],
        'qa': [r'\bqa\b', r'quality', r'\btest', r'sdet'],
        'manager': [r'manager', r'\blead\b', r'director', r'head of', r'vp ', r'principal'],
    }

    cached = redis_service.cache_get(f"{ANALYTICS_CACHE_PREFIX}by-job-type")
    if cached is not None:
        return cached

    # Only the titles are needed - don't load descriptions for every active job
    jobs = [row[0] for row in db.query(Job.title).filter(Job.is_active == True).all()]

    type_counts = {k: 0 for k in JOB_TYPE_PATTERNS.keys()}
    type_counts['other'] = 0

    for title in jobs:
        title_lower = (title or '').lower()
        matched = False

        for job_type, patterns in JOB_TYPE_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, title_lower, re.IGNORECASE):
                    type_counts[job_type] += 1
                    matched = True
                    break
            if matched:
                break

        if not matched:
            type_counts['other'] += 1

    # Return as list sorted by count
    result = [
        {"type": jtype, "count": count, "label": jtype.replace('_', ' ').title()}
        for jtype, count in sorted(type_counts.items(), key=lambda x: x[1], reverse=True)
        if count > 0
    ]

    payload = {"job_types": result, "total": len(jobs)}
    redis_service.cache_set(f"{ANALYTICS_CACHE_PREFIX}by-job-type", payload, settings.cache_ttl_analytics)
    return payload


@router.get("/interview-stats")
def get_interview_stats(db: Session = Depends(get_db)):
    """Get interview statistics."""
    def compute():
        base = db.query(Interview).join(Job)

        total_interviews = base.count()

        by_outcome = dict(
            db.query(Interview.outcome, func.count(Interview.id)).join(Job)
            .group_by(Interview.outcome).all()
        )
        outcome_counts = {o: by_outcome.get(o, 0) for o in ["pending", "passed", "failed", "cancelled"]}

        by_type = dict(
            db.query(Interview.interview_type, func.count(Interview.id)).join(Job)
            .group_by(Interview.interview_type).all()
        )
        type_counts = {t: by_type.get(t, 0) for t in ["phone_screen", "technical", "behavioral", "onsite", "final"]}

        # Upcoming interviews
        now = datetime.now()
        upcoming = base.options(joinedload(Interview.job).joinedload(Job.company)).filter(
            Interview.interview_date >= now,
            Interview.outcome == "pending"
        ).order_by(Interview.interview_date).limit(5).all()

        upcoming_list = [
            {
                "id": i.id,
                "job_id": i.job_id,
                "job_title": i.job.title if i.job else None,
                "company_name": i.job.company.name if i.job and i.job.company else None,
                "interview_date": i.interview_date,
                "interview_type": i.interview_type
            }
            for i in upcoming
        ]

        return {
            "total_interviews": total_interviews,
            "by_outcome": outcome_counts,
            "by_type": type_counts,
            "upcoming": upcoming_list
        }

    return _cached("interview-stats", compute)


@router.delete("/cleanup/old-jobs")
def cleanup_old_jobs(
    days: int = Query(default=7, ge=1, le=365, description="Delete jobs older than this many days"),
    dry_run: bool = Query(default=True, description="Preview without deleting"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Delete jobs where posted_date is older than the specified number of days.

    Admin-only endpoint. Related records (interviews, notes, documents) are also deleted.
    Use dry_run=true to preview before deleting.

    Filters by posted_date (when job was posted on company site), falling back to
    created_at for jobs without posted_date.
    """
    # Admin check
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Get jobs to delete - filter by posted_date (when job was posted)
    # For jobs without posted_date, fall back to created_at
    from sqlalchemy import or_, and_

    jobs_query = db.query(Job).filter(
        or_(
            # Jobs with posted_date older than cutoff
            and_(Job.posted_date.isnot(None), Job.posted_date < cutoff_date),
            # Jobs without posted_date, use created_at as fallback
            and_(Job.posted_date.is_(None), Job.created_at < cutoff_date)
        )
    )
    jobs_to_delete = jobs_query.all()
    job_ids = [job.id for job in jobs_to_delete]

    result = {
        "cutoff_date": cutoff_date.isoformat(),
        "dry_run": dry_run,
        "jobs_count": len(job_ids),
        "jobs_with_posted_date": sum(1 for j in jobs_to_delete if j.posted_date),
        "jobs_without_posted_date": sum(1 for j in jobs_to_delete if not j.posted_date),
        "interviews_count": 0,
        "notes_count": 0,
        "documents_count": 0,
    }

    if not job_ids:
        return result

    # Count related records
    result["interviews_count"] = db.query(Interview).filter(Interview.job_id.in_(job_ids)).count()
    result["notes_count"] = db.query(Note).filter(Note.job_id.in_(job_ids)).count()
    result["documents_count"] = db.query(Document).filter(Document.job_id.in_(job_ids)).count()

    if dry_run:
        return result

    # Delete related records first (those without CASCADE)
    db.query(Interview).filter(Interview.job_id.in_(job_ids)).delete(synchronize_session=False)
    db.query(Note).filter(Note.job_id.in_(job_ids)).delete(synchronize_session=False)
    db.query(Document).filter(Document.job_id.in_(job_ids)).delete(synchronize_session=False)

    # Delete jobs (cascades to job_relevance_scores, application_submissions)
    db.query(Job).filter(Job.id.in_(job_ids)).delete(synchronize_session=False)

    db.commit()
    redis_service.cache_delete_pattern(f"{ANALYTICS_CACHE_PREFIX}*")

    return result


@router.delete("/cleanup/duplicates")
def cleanup_duplicates(
    dry_run: bool = Query(default=True, description="Preview without deleting"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Find and remove duplicate jobs using multiple criteria:
    1. Same company_id + external_job_id (primary method)
    2. Same job_url (secondary method for jobs without external_job_id)

    Admin-only endpoint. Keeps the oldest job record and deletes newer duplicates.
    Use dry_run=true to preview before deleting.
    """
    # Admin check
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    duplicate_ids = set()

    # Method 1: Find duplicates by company_id + external_job_id
    duplicates_by_external_id = text("""
        SELECT j.id
        FROM jobs j
        INNER JOIN (
            SELECT company_id, external_job_id, MIN(id) as min_id
            FROM jobs
            WHERE external_job_id IS NOT NULL AND external_job_id != ''
            GROUP BY company_id, external_job_id
            HAVING COUNT(*) > 1
        ) dups ON j.company_id = dups.company_id
              AND j.external_job_id = dups.external_job_id
              AND j.id > dups.min_id
    """)

    result1 = db.execute(duplicates_by_external_id)
    for row in result1.fetchall():
        duplicate_ids.add(row[0])

    # Method 2: Find duplicates by job_url (for jobs without external_job_id)
    duplicates_by_url = text("""
        SELECT j.id
        FROM jobs j
        INNER JOIN (
            SELECT job_url, MIN(id) as min_id
            FROM jobs
            WHERE job_url IS NOT NULL AND job_url != ''
            GROUP BY job_url
            HAVING COUNT(*) > 1
        ) dups ON j.job_url = dups.job_url
              AND j.id > dups.min_id
    """)

    result2 = db.execute(duplicates_by_url)
    for row in result2.fetchall():
        duplicate_ids.add(row[0])

    # Method 3: Find duplicates by title + company_id + location
    # This catches cases where same job is posted multiple times with different URLs/IDs
    duplicates_by_title = text("""
        SELECT j.id
        FROM jobs j
        INNER JOIN (
            SELECT company_id, title, location, MIN(id) as min_id
            FROM jobs
            WHERE title IS NOT NULL AND title != ''
            GROUP BY company_id, title, location
            HAVING COUNT(*) > 1
        ) dups ON j.company_id = dups.company_id
              AND j.title = dups.title
              AND (j.location = dups.location OR (j.location IS NULL AND dups.location IS NULL))
              AND j.id > dups.min_id
    """)

    result3 = db.execute(duplicates_by_title)
    for row in result3.fetchall():
        duplicate_ids.add(row[0])

    duplicate_ids = list(duplicate_ids)

    response = {
        "dry_run": dry_run,
        "duplicates_count": len(duplicate_ids),
    }

    if not duplicate_ids:
        return response

    if dry_run:
        return response

    # Delete related records first
    db.query(Interview).filter(Interview.job_id.in_(duplicate_ids)).delete(synchronize_session=False)
    db.query(Note).filter(Note.job_id.in_(duplicate_ids)).delete(synchronize_session=False)
    db.query(Document).filter(Document.job_id.in_(duplicate_ids)).delete(synchronize_session=False)

    # Delete duplicate jobs
    db.query(Job).filter(Job.id.in_(duplicate_ids)).delete(synchronize_session=False)

    db.commit()
    redis_service.cache_delete_pattern(f"{ANALYTICS_CACHE_PREFIX}*")

    return response
