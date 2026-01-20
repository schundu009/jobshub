from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, true
from datetime import datetime, timedelta
from collections import defaultdict

from database import get_db
from models import Job, Company, Contact, Interview, User
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


def is_admin_user(user: User) -> bool:
    """Check if user has admin role."""
    return user.role == "admin"


@router.get("/summary")
async def get_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get dashboard summary statistics. Admin sees all data, users see their own."""
    is_admin = is_admin_user(current_user)

    # Build filters based on role
    if is_admin:
        # Admin sees all data
        jobs_base = db.query(Job)
        companies_base = db.query(Company)
        contacts_base = db.query(Contact)
    else:
        # Regular users see only their data
        jobs_base = db.query(Job).filter(Job.user_id == current_user.id)
        companies_base = db.query(Company).filter(Company.user_id == current_user.id)
        contacts_base = db.query(Contact).filter(Contact.user_id == current_user.id)

    # Count only active jobs (consistent with jobs page)
    total_jobs = jobs_base.filter(Job.is_active == True).count()
    total_companies = companies_base.count()
    total_contacts = contacts_base.count()

    status_counts = {}
    for status in ["wishlist", "applied", "interviewing", "offer", "rejected", "withdrawn"]:
        status_counts[status] = jobs_base.filter(
            Job.status == status,
            Job.is_active == True
        ).count()

    now = datetime.now()
    week_later = now + timedelta(days=7)

    if is_admin:
        upcoming_interviews = db.query(Interview).join(Job).filter(
            Interview.interview_date >= now,
            Interview.interview_date <= week_later,
            Interview.outcome == "pending"
        ).count()
        recent_jobs = db.query(Job).order_by(Job.created_at.desc()).limit(5).all()
    else:
        upcoming_interviews = db.query(Interview).join(Job).filter(
            Interview.interview_date >= now,
            Interview.interview_date <= week_later,
            Interview.outcome == "pending",
            Job.user_id == current_user.id
        ).count()
        recent_jobs = db.query(Job).filter(Job.user_id == current_user.id).order_by(Job.created_at.desc()).limit(5).all()

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
async def get_status_breakdown(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed breakdown of jobs by status. Admin sees all, users see their own."""
    is_admin = is_admin_user(current_user)
    statuses = ["wishlist", "applied", "interviewing", "offer", "rejected", "withdrawn"]
    breakdown = []

    if is_admin:
        jobs_base = db.query(Job)
    else:
        jobs_base = db.query(Job).filter(Job.user_id == current_user.id)

    total = jobs_base.count()

    for status in statuses:
        count = jobs_base.filter(Job.status == status).count()
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
async def get_timeline(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get applications over time (last 30 days). Admin sees all, users see their own."""
    is_admin = is_admin_user(current_user)
    now = datetime.now()
    thirty_days_ago = now - timedelta(days=30)

    if is_admin:
        jobs = db.query(Job).filter(Job.created_at >= thirty_days_ago).all()
    else:
        jobs = db.query(Job).filter(
            Job.created_at >= thirty_days_ago,
            Job.user_id == current_user.id
        ).all()

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
async def get_response_rate(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Calculate response rate and success metrics. Admin sees all, users see their own."""
    is_admin = is_admin_user(current_user)

    if is_admin:
        jobs_base = db.query(Job)
    else:
        jobs_base = db.query(Job).filter(Job.user_id == current_user.id)

    total_applied = jobs_base.filter(Job.status != "wishlist").count()
    got_interview = jobs_base.filter(Job.status.in_(["interviewing", "offer"])).count()
    got_offer = jobs_base.filter(Job.status == "offer").count()
    rejected = jobs_base.filter(Job.status == "rejected").count()

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
async def get_jobs_by_company(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get job applications grouped by company. Admin sees all, users see their own."""
    is_admin = is_admin_user(current_user)

    if is_admin:
        companies = db.query(Company).all()
    else:
        companies = db.query(Company).filter(Company.user_id == current_user.id).all()

    result = []

    for company in companies:
        if is_admin:
            user_jobs = company.jobs
        else:
            user_jobs = [j for j in company.jobs if j.user_id == current_user.id]

        job_count = len(user_jobs)
        if job_count > 0:
            status_breakdown = {}
            for job in user_jobs:
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
async def get_jobs_by_location(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get job applications grouped by location. Admin sees all, users see their own."""
    is_admin = is_admin_user(current_user)

    if is_admin:
        jobs = db.query(Job).all()
    else:
        jobs = db.query(Job).filter(Job.user_id == current_user.id).all()

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
async def get_excitement_distribution(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get distribution of excitement levels. Admin sees all, users see their own."""
    is_admin = is_admin_user(current_user)

    if is_admin:
        jobs_base = db.query(Job)
    else:
        jobs_base = db.query(Job).filter(Job.user_id == current_user.id)

    distribution = []

    for level in range(1, 6):
        count = jobs_base.filter(Job.excitement_level == level).count()
        distribution.append({
            "level": level,
            "count": count
        })

    if is_admin:
        avg_excitement = db.query(func.avg(Job.excitement_level)).scalar()
    else:
        avg_excitement = db.query(func.avg(Job.excitement_level)).filter(Job.user_id == current_user.id).scalar()

    avg_excitement = round(float(avg_excitement), 2) if avg_excitement else 0

    return {
        "distribution": distribution,
        "average": avg_excitement
    }


@router.get("/interview-stats")
async def get_interview_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get interview statistics. Admin sees all, users see their own."""
    is_admin = is_admin_user(current_user)

    if is_admin:
        interviews_base = db.query(Interview).join(Job)
    else:
        interviews_base = db.query(Interview).join(Job).filter(Job.user_id == current_user.id)

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
