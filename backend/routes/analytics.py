from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, true, text
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Optional

from database import get_db
from models import Job, Company, Contact, Interview, Note, Document, User
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
async def get_summary(db: Session = Depends(get_db)):
    """Get dashboard summary statistics."""
    # Count only active jobs
    total_jobs = db.query(Job).filter(Job.is_active == True).count()
    total_companies = db.query(Company).count()
    total_contacts = db.query(Contact).count()

    status_counts = {}
    for status in ["wishlist", "applied", "interviewing", "offer", "rejected", "withdrawn"]:
        status_counts[status] = db.query(Job).filter(
            Job.status == status,
            Job.is_active == True
        ).count()

    now = datetime.now()
    week_later = now + timedelta(days=7)

    upcoming_interviews = db.query(Interview).join(Job).filter(
        Interview.interview_date >= now,
        Interview.interview_date <= week_later,
        Interview.outcome == "pending"
    ).count()

    recent_jobs = db.query(Job).order_by(Job.created_at.desc()).limit(5).all()

    recent_activity = [
        {
            "id": j.id,
            "title": j.title,
            "company_name": j.company.name if j.company else None,
            "status": j.status,
            "created_at": j.created_at
        } for j in recent_jobs
    ]

    return {
        "total_jobs": total_jobs,
        "total_companies": total_companies,
        "total_contacts": total_contacts,
        "status_counts": status_counts,
        "upcoming_interviews": upcoming_interviews,
        "recent_activity": recent_activity
    }


@router.get("/status-breakdown")
async def get_status_breakdown(db: Session = Depends(get_db)):
    """Get detailed breakdown of jobs by status."""
    statuses = ["wishlist", "applied", "interviewing", "offer", "rejected", "withdrawn"]
    breakdown = []

    total = db.query(Job).count()

    for status in statuses:
        count = db.query(Job).filter(Job.status == status).count()
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


@router.get("/timeline")
async def get_timeline(db: Session = Depends(get_db)):
    """Get applications over time (last 30 days)."""
    now = datetime.now()
    thirty_days_ago = now - timedelta(days=30)

    jobs = db.query(Job).filter(Job.created_at >= thirty_days_ago).all()

    # Group by date
    daily_counts = defaultdict(int)
    for job in jobs:
        if job.created_at:
            date_str = job.created_at.strftime("%Y-%m-%d")
            daily_counts[date_str] += 1

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


@router.get("/response-rate")
async def get_response_rate(db: Session = Depends(get_db)):
    """Calculate response rate and success metrics."""
    total_applied = db.query(Job).filter(Job.status != "wishlist").count()
    got_interview = db.query(Job).filter(Job.status.in_(["interviewing", "offer"])).count()
    got_offer = db.query(Job).filter(Job.status == "offer").count()
    rejected = db.query(Job).filter(Job.status == "rejected").count()

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


@router.get("/by-company")
async def get_jobs_by_company(db: Session = Depends(get_db)):
    """Get job applications grouped by company."""
    companies = db.query(Company).all()
    result = []

    for company in companies:
        job_count = len(company.jobs)
        if job_count > 0:
            status_breakdown = {}
            for job in company.jobs:
                status_breakdown[job.status] = status_breakdown.get(job.status, 0) + 1

            result.append({
                "company_id": company.id,
                "company_name": company.name,
                "job_count": job_count,
                "status_breakdown": status_breakdown
            })

    # Sort by job count descending
    result.sort(key=lambda x: x["job_count"], reverse=True)

    return {"companies": result}


@router.get("/by-location")
async def get_jobs_by_location(db: Session = Depends(get_db)):
    """Get job applications grouped by location."""
    jobs = db.query(Job).all()

    location_counts = defaultdict(int)
    for job in jobs:
        location = job.location or "Not specified"
        location_counts[location] += 1

    result = [
        {"location": loc, "count": count}
        for loc, count in sorted(location_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return {"locations": result}


@router.get("/excitement-distribution")
async def get_excitement_distribution(db: Session = Depends(get_db)):
    """Get distribution of excitement levels."""
    distribution = []

    for level in range(1, 6):
        count = db.query(Job).filter(Job.excitement_level == level).count()
        distribution.append({
            "level": level,
            "count": count
        })

    avg_excitement = db.query(func.avg(Job.excitement_level)).scalar()
    avg_excitement = round(float(avg_excitement), 2) if avg_excitement else 0

    return {
        "distribution": distribution,
        "average": avg_excitement
    }


@router.get("/by-job-type")
async def get_jobs_by_type(db: Session = Depends(get_db)):
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

    jobs = db.query(Job).filter(Job.is_active == True).all()

    type_counts = {k: 0 for k in JOB_TYPE_PATTERNS.keys()}
    type_counts['other'] = 0

    for job in jobs:
        title_lower = (job.title or '').lower()
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

    return {"job_types": result, "total": len(jobs)}


@router.get("/interview-stats")
async def get_interview_stats(db: Session = Depends(get_db)):
    """Get interview statistics."""
    interviews_base = db.query(Interview).join(Job)

    total_interviews = interviews_base.count()

    outcome_counts = {}
    for outcome in ["pending", "passed", "failed", "cancelled"]:
        outcome_counts[outcome] = interviews_base.filter(Interview.outcome == outcome).count()

    type_counts = {}
    for itype in ["phone_screen", "technical", "behavioral", "onsite", "final"]:
        type_counts[itype] = interviews_base.filter(Interview.interview_type == itype).count()

    # Upcoming interviews
    now = datetime.now()
    upcoming = interviews_base.filter(
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


@router.delete("/cleanup/old-jobs")
async def cleanup_old_jobs(
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

    return result


@router.delete("/cleanup/duplicates")
async def cleanup_duplicates(
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

    return response
