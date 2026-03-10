"""
Apify Integration API Routes.

Endpoints for:
- Running Apify job scrapers (LinkedIn, Indeed, Glassdoor)
- Checking Apify configuration status
- Managing Apify scraper runs
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from middleware.auth import get_current_user
from models import User, Job, Company
from services.apify_service import get_apify_service, APIFY_ACTORS, APIFY_AVAILABLE

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/apify", tags=["apify"])


# ============== Pydantic Models ==============

class ApifyStatusResponse(BaseModel):
    configured: bool
    available_actors: list[dict]


class ApifyRunRequest(BaseModel):
    actor_key: str = Field(..., description="Actor key (linkedin_jobs, indeed_jobs, glassdoor_jobs)")
    search_queries: list[str] = Field(
        default=["software engineer"],
        description="Job search queries"
    )
    location: str = Field(default="United States", description="Location to search")
    max_items: int = Field(default=100, ge=10, le=500, description="Maximum jobs to fetch")


class ApifyRunResponse(BaseModel):
    status: str
    actor_key: str
    jobs_found: int
    jobs_saved: int
    companies_created: int
    duration_seconds: float
    error: Optional[str] = None


class ApifyQuickRunResponse(BaseModel):
    status: str
    message: str
    task_started: bool


# ============== Helper Functions ==============

def save_apify_jobs(db: Session, jobs: list[dict], source: str) -> tuple[int, int]:
    """
    Save jobs from Apify to database.

    Args:
        db: Database session
        jobs: List of parsed jobs from Apify
        source: Source identifier (linkedin, indeed, glassdoor)

    Returns:
        Tuple of (jobs_saved, companies_created)
    """
    jobs_saved = 0
    companies_created = 0
    companies_cache = {}
    skipped_existing = 0

    logger.info(f"save_apify_jobs: Processing {len(jobs)} jobs from {source}")

    for job_data in jobs:
        try:
            # Get or create company - check raw_data for company_name
            raw_data = job_data.get("raw_data", {}) or {}
            company_name = raw_data.get("company_name") or job_data.get("company_name", "Unknown")

            if company_name not in companies_cache:
                company = db.query(Company).filter(
                    Company.name == company_name
                ).first()

                if not company:
                    # Create company
                    import re
                    slug = re.sub(r'[^a-z0-9]+', '-', company_name.lower()).strip('-')

                    company = Company(
                        name=company_name,
                        slug=slug,
                        careers_url=job_data.get("job_url", "").split("/job")[0] if job_data.get("job_url") else None,
                        source=source,
                    )
                    db.add(company)
                    db.flush()
                    companies_created += 1

                companies_cache[company_name] = company

            company = companies_cache[company_name]

            # Check if job already exists
            external_job_id = job_data.get("external_job_id", "")
            if external_job_id:
                existing = db.query(Job).filter(
                    Job.company_id == company.id,
                    Job.external_job_id == external_job_id
                ).first()

                if existing:
                    # Update existing job
                    existing.title = job_data.get("title", existing.title)
                    existing.description = job_data.get("job_description") or job_data.get("description") or existing.description
                    existing.location = job_data.get("location") or existing.location
                    existing.updated_at = datetime.utcnow()
                    skipped_existing += 1
                    continue

            # Create new job
            job = Job(
                title=job_data.get("title", ""),
                company_id=company.id,
                location=job_data.get("location", ""),
                job_url=job_data.get("job_url", ""),
                external_job_id=external_job_id,
                description=job_data.get("job_description") or job_data.get("description", ""),
                department=job_data.get("department", ""),
                salary_min=job_data.get("salary_min"),
                salary_max=job_data.get("salary_max"),
                employment_type=job_data.get("employment_type", ""),
                remote_type=job_data.get("remote_type"),
                source=source,
                is_active=True,
                status="wishlist",
            )

            # Parse posted date
            posted_date = job_data.get("posted_date")
            if posted_date:
                if isinstance(posted_date, str):
                    try:
                        from dateutil import parser
                        job.posted_date = parser.parse(posted_date)
                    except:
                        pass
                elif isinstance(posted_date, datetime):
                    job.posted_date = posted_date

            db.add(job)
            jobs_saved += 1

        except Exception as e:
            logger.error(f"Failed to save job: {e}", exc_info=True)
            continue

    try:
        db.commit()
        logger.info(f"save_apify_jobs: Saved {jobs_saved} new jobs, {companies_created} companies, skipped {skipped_existing} existing")
    except Exception as e:
        logger.error(f"Failed to commit: {e}", exc_info=True)
        db.rollback()
        return 0, 0

    return jobs_saved, companies_created


# ============== Endpoints ==============

@router.get("/status", response_model=ApifyStatusResponse)
def get_apify_status(current_user: User = Depends(get_current_user)):
    """
    Check Apify configuration status.

    Returns whether Apify is configured and available actors.
    """
    service = get_apify_service()

    return ApifyStatusResponse(
        configured=service.is_configured,
        available_actors=service.list_available_actors()
    )


@router.post("/run", response_model=ApifyRunResponse)
async def run_apify_scraper(
    request: ApifyRunRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Run an Apify scraper and save results.

    This runs synchronously and returns when complete.
    For background execution, use /run-async endpoint.
    """
    service = get_apify_service()

    if not service.is_configured:
        raise HTTPException(
            status_code=400,
            detail="Apify not configured. Set APIFY_API_TOKEN environment variable."
        )

    if request.actor_key not in APIFY_ACTORS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown actor: {request.actor_key}. Available: {list(APIFY_ACTORS.keys())}"
        )

    start_time = datetime.utcnow()

    # Run the actor
    result = await service.run_actor(
        actor_key=request.actor_key,
        input_override={
            "searchQueries": request.search_queries,
            "location": request.location,
            "maxItems": request.max_items,
        },
        wait_for_finish=True,
    )

    if result.get("status") == "error":
        return ApifyRunResponse(
            status="error",
            actor_key=request.actor_key,
            jobs_found=0,
            jobs_saved=0,
            companies_created=0,
            duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
            error=result.get("error"),
        )

    # Save jobs to database
    jobs = result.get("jobs", [])
    source = request.actor_key.replace("_jobs", "").replace("_", "")  # linkedin, indeed, glassdoor

    jobs_saved, companies_created = save_apify_jobs(db, jobs, source)

    return ApifyRunResponse(
        status="success",
        actor_key=request.actor_key,
        jobs_found=len(jobs),
        jobs_saved=jobs_saved,
        companies_created=companies_created,
        duration_seconds=result.get("duration_seconds", 0),
    )


@router.post("/run-quick/{actor_key}", response_model=ApifyQuickRunResponse)
async def run_apify_quick(
    actor_key: str,
    background_tasks: BackgroundTasks,
    search_query: str = Query(default="software engineer"),
    location: str = Query(default="United States"),
    max_items: int = Query(default=50, ge=10, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Quick endpoint to run an Apify scraper in the background.

    Returns immediately while scraping continues in background.
    """
    service = get_apify_service()

    if not service.is_configured:
        return ApifyQuickRunResponse(
            status="error",
            message="Apify not configured. Set APIFY_API_TOKEN.",
            task_started=False
        )

    if actor_key not in APIFY_ACTORS:
        return ApifyQuickRunResponse(
            status="error",
            message=f"Unknown actor: {actor_key}",
            task_started=False
        )

    # Define background task
    async def run_scraper():
        try:
            result = await service.run_actor(
                actor_key=actor_key,
                input_override={
                    "searchQueries": [search_query],
                    "location": location,
                    "maxItems": max_items,
                },
                wait_for_finish=True,
            )

            if result.get("status") == "success":
                jobs = result.get("jobs", [])
                source = actor_key.replace("_jobs", "").replace("_", "")
                # Note: Need fresh db session for background task
                from database import SessionLocal
                with SessionLocal() as bg_db:
                    save_apify_jobs(bg_db, jobs, source)
                logger.info(f"Apify {actor_key}: Saved {len(jobs)} jobs")
            else:
                logger.error(f"Apify {actor_key} failed: {result.get('error')}")

        except Exception as e:
            logger.exception(f"Background Apify task failed: {e}")

    background_tasks.add_task(run_scraper)

    return ApifyQuickRunResponse(
        status="started",
        message=f"Started {actor_key} scraper for '{search_query}' in {location}",
        task_started=True
    )


@router.post("/run-all")
async def run_all_apify_scrapers(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """
    Run all configured Apify scrapers in the background.

    This is useful for initial data population or periodic refresh.
    """
    service = get_apify_service()

    if not service.is_configured:
        raise HTTPException(
            status_code=400,
            detail="Apify not configured. Set APIFY_API_TOKEN."
        )

    # Default search queries for each actor
    default_queries = {
        "linkedin_jobs": [
            "software engineer",
            "data engineer",
            "devops engineer",
            "machine learning engineer",
        ],
        "indeed_jobs": [
            "software engineer",
            "backend developer",
            "frontend developer",
        ],
    }

    async def run_all():
        from database import SessionLocal

        for actor_key, queries in default_queries.items():
            try:
                for query in queries:
                    result = await service.run_actor(
                        actor_key=actor_key,
                        input_override={
                            "searchQueries": [query],
                            "location": "United States",
                            "maxItems": 50,
                        },
                        wait_for_finish=True,
                    )

                    if result.get("status") == "success":
                        jobs = result.get("jobs", [])
                        source = actor_key.replace("_jobs", "").replace("_", "")
                        with SessionLocal() as bg_db:
                            saved, created = save_apify_jobs(bg_db, jobs, source)
                            logger.info(f"Apify {actor_key}/{query}: {saved} jobs saved, {created} companies created")

            except Exception as e:
                logger.exception(f"Error running {actor_key}: {e}")

    background_tasks.add_task(run_all)

    return {
        "status": "started",
        "message": "Started all Apify scrapers in background",
        "actors": list(default_queries.keys()),
    }


# ============== Webhook for External Triggers ==============

@router.post("/webhook/trigger")
async def webhook_trigger_apify(
    secret: str = Query(..., description="Webhook secret"),
    actor_key: str = Query(default="linkedin_jobs"),
    search_query: str = Query(default="software engineer"),
):
    """
    Trigger Apify scraper via webhook (no auth required, uses secret).

    Use this for external triggers like cron jobs.
    """
    import os
    expected_secret = os.environ.get("APIFY_WEBHOOK_SECRET", "apify-cariara-2024")

    if secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    service = get_apify_service()

    if not service.is_configured:
        raise HTTPException(status_code=400, detail="Apify not configured")

    # Run synchronously for webhook (can track completion)
    result = await service.run_actor(
        actor_key=actor_key,
        input_override={
            "searchQueries": [search_query],
            "location": "United States",
            "maxItems": 100,
        },
        wait_for_finish=True,
    )

    if result.get("status") == "success":
        from database import SessionLocal
        with SessionLocal() as db:
            jobs = result.get("jobs", [])
            source = actor_key.replace("_jobs", "").replace("_", "")
            saved, created = save_apify_jobs(db, jobs, source)

            return {
                "status": "success",
                "jobs_found": len(jobs),
                "jobs_saved": saved,
                "companies_created": created,
            }

    return {
        "status": "error",
        "error": result.get("error"),
    }


@router.get("/debug")
def debug_apify_config():
    """Debug endpoint to check Apify configuration (temporary)."""
    import os

    service = get_apify_service()
    token = os.environ.get("APIFY_API_TOKEN", "")

    return {
        "apify_available": APIFY_AVAILABLE,
        "token_set": bool(token),
        "token_length": len(token) if token else 0,
        "token_prefix": token[:10] + "..." if len(token) > 10 else token,
        "is_configured": service.is_configured,
        "service_token_set": bool(service.api_token),
    }


@router.post("/test-sample")
async def test_apify_sample(db: Session = Depends(get_db)):
    """Test endpoint to fetch sample jobs, save them, and return details."""
    service = get_apify_service()

    if not service.is_configured:
        return {"error": "Apify not configured"}

    result = await service.run_actor(
        actor_key="indeed_jobs",
        input_override={
            "searchQueries": ["python developer"],
            "location": "Boston",  # Use different location for fresh jobs
            "maxItems": 5,
        },
        wait_for_finish=True,
    )

    jobs = result.get("jobs", [])

    # Try to save and report results
    saved, created = save_apify_jobs(db, jobs, "indeed")

    return {
        "status": result.get("status"),
        "jobs_found": result.get("jobs_found", 0),
        "jobs_saved": saved,
        "companies_created": created,
        "sample_jobs": jobs[:2],  # Return first 2 for inspection
    }
