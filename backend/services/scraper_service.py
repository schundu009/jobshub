"""
Scraper Service - Orchestration and job saving for custom scrapers.

Provides:
- save_scraped_jobs: Save or update jobs from scrapers
- get_or_create_company: Get or create a company record
- Job deduplication and update logic
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models import Company, Job
from scrapers.base import ScrapedJob
from scrapers.registry import ScraperRegistry

logger = logging.getLogger(__name__)

# Only save jobs posted within this many days
MAX_JOB_AGE_DAYS = 7


def get_or_create_company(
    db: Session,
    company_slug: str,
    company_name: Optional[str] = None,
    website: Optional[str] = None,
) -> Company:
    """
    Get an existing company or create a new one.

    Args:
        db: Database session
        company_slug: Company slug (used as identifier)
        company_name: Display name (optional)
        website: Company website (optional)

    Returns:
        Company record
    """
    # Try to find by name first
    name = company_name or company_slug.replace("-", " ").replace("_", " ").title()

    company = db.query(Company).filter(
        Company.name.ilike(name)
    ).first()

    if company:
        return company

    # Create new company
    company = Company(
        name=name,
        website=website,
    )
    db.add(company)
    db.flush()  # Get the ID without committing

    logger.info(f"Created new company: {name} (ID: {company.id})")
    return company


def save_scraped_jobs(
    db: Session,
    company_slug: str,
    jobs: list[ScrapedJob],
) -> tuple[int, int]:
    """
    Save or update scraped jobs in the database.

    Jobs are matched by external_job_id. New jobs are created,
    existing jobs are updated with fresh data.

    Args:
        db: Database session
        company_slug: Company slug (used as source identifier)
        jobs: List of ScrapedJob objects

    Returns:
        Tuple of (jobs_new, jobs_updated)
    """
    if not jobs:
        return 0, 0

    # Get scraper metadata for company info
    metadata = ScraperRegistry.get_metadata(company_slug)
    company_name = metadata["company_name"] if metadata else None
    careers_url = metadata["careers_url"] if metadata else None

    # Get or create company
    company = get_or_create_company(
        db,
        company_slug,
        company_name=company_name,
        website=careers_url,
    )

    jobs_new = 0
    jobs_updated = 0
    jobs_skipped_old = 0
    cutoff_date = datetime.utcnow() - timedelta(days=MAX_JOB_AGE_DAYS)

    for scraped_job in jobs:
        try:
            # Skip jobs older than MAX_JOB_AGE_DAYS
            if scraped_job.posted_date and scraped_job.posted_date < cutoff_date:
                jobs_skipped_old += 1
                continue

            # Generate external ID if not provided
            external_id = scraped_job.external_job_id or scraped_job.generate_id()

            # Try to find existing job
            existing = db.query(Job).filter(
                Job.company_id == company.id,
                Job.external_job_id == external_id,
            ).first()

            if existing:
                # Update existing job
                existing.title = scraped_job.title
                existing.location = scraped_job.location or existing.location
                existing.job_url = scraped_job.job_url
                existing.job_description = scraped_job.job_description or existing.job_description
                existing.department = scraped_job.department or existing.department
                existing.posted_date = scraped_job.posted_date or existing.posted_date
                existing.salary_min = scraped_job.salary_min or existing.salary_min
                existing.salary_max = scraped_job.salary_max or existing.salary_max
                existing.is_active = True  # Mark as still active
                existing.updated_at = datetime.utcnow()
                jobs_updated += 1

            else:
                # Create new job
                job = Job(
                    title=scraped_job.title,
                    company_id=company.id,
                    location=scraped_job.location,
                    job_url=scraped_job.job_url,
                    job_description=scraped_job.job_description,
                    department=scraped_job.department,
                    posted_date=scraped_job.posted_date,
                    salary_min=scraped_job.salary_min,
                    salary_max=scraped_job.salary_max,
                    source=company_slug,
                    external_job_id=external_id,
                    is_active=True,
                    status="wishlist",
                    date_found=datetime.utcnow().date(),
                )
                db.add(job)
                # Use savepoint to catch duplicate key violations without rolling back entire transaction
                try:
                    # Create a savepoint before flush
                    savepoint = db.begin_nested()
                    db.flush()
                    jobs_new += 1
                except IntegrityError:
                    # Duplicate key - rollback only to savepoint, not entire transaction
                    try:
                        savepoint.rollback()
                    except Exception:
                        pass  # Ignore rollback errors - connection may already be bad
                    logger.debug(f"Duplicate job skipped: {scraped_job.title} ({external_id})")
                    jobs_updated += 1  # Count as update since job exists
                    continue
                except Exception as e:
                    # Any other database error - try to rollback savepoint
                    try:
                        savepoint.rollback()
                    except Exception:
                        pass
                    logger.warning(f"Database error saving job, skipping: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error saving job '{scraped_job.title}': {e}")
            continue

    # Commit with error handling
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit jobs for {company_slug}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return 0, 0

    logger.info(
        f"Saved jobs for {company_slug}: {jobs_new} new, {jobs_updated} updated"
        + (f", {jobs_skipped_old} skipped (older than {MAX_JOB_AGE_DAYS} days)" if jobs_skipped_old else "")
    )

    return jobs_new, jobs_updated


def mark_jobs_inactive(
    db: Session,
    company_slug: str,
    active_external_ids: set[str],
):
    """
    Mark jobs that are no longer on the career page as inactive.

    Args:
        db: Database session
        company_slug: Company slug
        active_external_ids: Set of external IDs still active
    """
    # Get company
    metadata = ScraperRegistry.get_metadata(company_slug)
    if not metadata:
        return

    company = db.query(Company).filter(
        Company.name.ilike(metadata["company_name"])
    ).first()

    if not company:
        return

    # Find jobs to mark inactive
    inactive_count = db.query(Job).filter(
        Job.company_id == company.id,
        Job.source == company_slug,
        Job.is_active == True,
        ~Job.external_job_id.in_(active_external_ids),
    ).update({"is_active": False}, synchronize_session=False)

    db.commit()

    if inactive_count:
        logger.info(f"Marked {inactive_count} jobs inactive for {company_slug}")


def get_scraper_stats(db: Session, company_slug: str) -> dict:
    """
    Get statistics for a scraper.

    Args:
        db: Database session
        company_slug: Company slug

    Returns:
        Dict with statistics
    """
    from models import ScraperRun, ScraperConfigDB

    config = db.query(ScraperConfigDB).filter(
        ScraperConfigDB.company_slug == company_slug
    ).first()

    # Get recent runs
    recent_runs = db.query(ScraperRun).filter(
        ScraperRun.company_slug == company_slug
    ).order_by(ScraperRun.run_at.desc()).limit(10).all()

    # Get job counts
    metadata = ScraperRegistry.get_metadata(company_slug)
    company_name = metadata["company_name"] if metadata else company_slug

    company = db.query(Company).filter(
        Company.name.ilike(company_name)
    ).first()

    active_jobs = 0
    total_jobs = 0
    if company:
        active_jobs = db.query(Job).filter(
            Job.company_id == company.id,
            Job.is_active == True,
        ).count()
        total_jobs = db.query(Job).filter(
            Job.company_id == company.id,
        ).count()

    # Get last error from most recent failed run
    last_error = None
    for run in recent_runs:
        if not run.success and run.error_message:
            last_error = run.error_message
            break

    return {
        "company_slug": company_slug,
        "company_name": company_name,
        "is_enabled": config.is_enabled if config else True,
        "consecutive_failures": config.consecutive_failures if config else 0,
        "total_runs": config.total_runs if config else 0,
        "last_success_at": config.last_success_at.isoformat() if config and config.last_success_at else None,
        "last_failure_at": config.last_failure_at.isoformat() if config and config.last_failure_at else None,
        "last_error": last_error,
        "active_jobs": active_jobs,
        "total_jobs": total_jobs,
        "recent_runs": [
            {
                "id": run.id,
                "success": run.success,
                "jobs_found": run.jobs_found,
                "duration_seconds": run.duration_seconds,
                "error_message": run.error_message,
                "run_at": run.run_at.isoformat() if run.run_at else None,
            }
            for run in recent_runs
        ],
    }
