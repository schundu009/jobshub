from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, true
from datetime import datetime, timedelta
from collections import defaultdict

from database import get_db
from models import Job, Company, Contact, Interview

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
