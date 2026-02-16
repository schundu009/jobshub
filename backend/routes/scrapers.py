"""
Scraper Management API Routes.

Endpoints for:
- Listing available scrapers
- Triggering scraper runs
- Viewing scraper status and history
- Enabling/disabling scrapers

Security features:
- JWT authentication required for all endpoints
- SSRF protection on URL validation
- Input validation and length limits
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
import re
from sqlalchemy.orm import Session

from database import get_db
from models import ScraperRun, ScraperConfigDB, User
from scrapers.registry import ScraperRegistry, list_all_scrapers
from services.scraper_service import get_scraper_stats
from utils.security import validate_url_ssrf_safe
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/scrapers", tags=["scrapers"])


# ============== Pydantic Models ==============

class ScraperInfo(BaseModel):
    slug: str
    company_name: str
    scraper_type: str
    careers_url: str
    category: str
    rate_limit: int


class ScraperStatus(BaseModel):
    company_slug: str
    company_name: str
    is_enabled: bool
    consecutive_failures: int
    total_runs: int
    last_success_at: Optional[str]
    last_failure_at: Optional[str]
    last_error: Optional[str] = None
    active_jobs: int
    total_jobs: int


class ScraperRunInfo(BaseModel):
    id: int
    success: bool
    jobs_found: int
    jobs_new: int
    jobs_updated: int
    duration_seconds: Optional[float]
    error_message: Optional[str]
    error_type: Optional[str]
    run_at: str


class TriggerResponse(BaseModel):
    status: str
    task_id: Optional[str]
    message: str


class ConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    config_overrides: Optional[dict] = None


class CustomCompanyRequest(BaseModel):
    company_name: str = Field(..., min_length=2, max_length=255)
    careers_url: str = Field(..., min_length=10, max_length=500)

    @field_validator('careers_url')
    @classmethod
    def validate_url(cls, v):
        is_valid, error = validate_url_ssrf_safe(v)
        if not is_valid:
            raise ValueError(error)
        return v


class CustomCompanyResponse(BaseModel):
    status: str
    slug: str
    company_name: str
    board_type: str
    job_count: int
    message: str
    task_id: Optional[str] = None


class DetectBoardResponse(BaseModel):
    board_type: str
    valid: bool
    job_count: int
    api_url: Optional[str]
    error: Optional[str]


# ============== Endpoints ==============

@router.get("/", response_model=list[ScraperInfo])
def list_scrapers(
    category: Optional[str] = Query(None, description="Filter by category"),
    scraper_type: Optional[str] = Query(None, description="Filter by type (http, playwright)"),
    current_user: User = Depends(get_current_user),
):
    """
    List all available scrapers.

    Returns scrapers with their metadata and configuration.
    """
    scrapers = list_all_scrapers()

    if category:
        scrapers = [s for s in scrapers if s.get("category") == category]

    if scraper_type:
        scrapers = [s for s in scrapers if s.get("scraper_type") == scraper_type]

    return scrapers


@router.get("/categories")
def list_categories(current_user: User = Depends(get_current_user)):
    """List all scraper categories."""
    return {"categories": ScraperRegistry.list_categories()}


@router.get("/status", response_model=list[ScraperStatus])
def get_all_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get status of all scrapers.

    Returns health metrics for each scraper.
    """
    slugs = ScraperRegistry.list_slugs()
    statuses = []

    for slug in slugs:
        stats = get_scraper_stats(db, slug)
        statuses.append(ScraperStatus(
            company_slug=stats["company_slug"],
            company_name=stats["company_name"],
            is_enabled=stats["is_enabled"],
            consecutive_failures=stats["consecutive_failures"],
            total_runs=stats["total_runs"],
            last_success_at=stats["last_success_at"],
            last_failure_at=stats["last_failure_at"],
            last_error=stats.get("last_error"),
            active_jobs=stats["active_jobs"],
            total_jobs=stats["total_jobs"],
        ))

    return statuses


@router.get("/{company_slug}")
def get_scraper_detail(
    company_slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get detailed information about a scraper.

    Includes recent run history and job counts.
    """
    scraper_cls = ScraperRegistry.get(company_slug)
    if not scraper_cls:
        raise HTTPException(status_code=404, detail="Scraper not found")

    stats = get_scraper_stats(db, company_slug)
    metadata = ScraperRegistry.get_metadata(company_slug)

    return {
        **stats,
        "scraper_type": metadata.get("scraper_type"),
        "careers_url": metadata.get("careers_url"),
        "category": metadata.get("category"),
        "rate_limit": metadata.get("rate_limit"),
    }


@router.get("/{company_slug}/runs", response_model=list[ScraperRunInfo])
def get_scraper_runs(
    company_slug: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Get run history for a scraper.
    """
    runs = db.query(ScraperRun).filter(
        ScraperRun.company_slug == company_slug
    ).order_by(ScraperRun.run_at.desc()).offset(offset).limit(limit).all()

    return [
        ScraperRunInfo(
            id=run.id,
            success=run.success,
            jobs_found=run.jobs_found,
            jobs_new=run.jobs_new or 0,
            jobs_updated=run.jobs_updated or 0,
            duration_seconds=run.duration_seconds,
            error_message=run.error_message,
            error_type=run.error_type,
            run_at=run.run_at.isoformat() if run.run_at else "",
        )
        for run in runs
    ]


@router.post("/{company_slug}/run", response_model=TriggerResponse)
def trigger_scraper(
    company_slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Trigger a scraper run for a company.

    Dispatches a Celery task and returns the task ID.
    """
    scraper_cls = ScraperRegistry.get(company_slug)
    if not scraper_cls:
        raise HTTPException(status_code=404, detail="Scraper not found")

    # Check if enabled
    config = db.query(ScraperConfigDB).filter(
        ScraperConfigDB.company_slug == company_slug
    ).first()

    if config and not config.is_enabled:
        raise HTTPException(status_code=400, detail="Scraper is disabled")

    # Import tasks here to avoid circular imports
    from tasks.scraper_tasks import scrape_company_http, scrape_company_browser
    from scrapers.base import ScraperType

    # Dispatch appropriate task
    if scraper_cls.config.scraper_type == ScraperType.HTTP:
        task = scrape_company_http.delay(company_slug)
    else:
        task = scrape_company_browser.delay(company_slug)

    return TriggerResponse(
        status="dispatched",
        task_id=task.id,
        message=f"Scrape task dispatched for {company_slug}",
    )


@router.post("/run-all", response_model=TriggerResponse)
def trigger_all_scrapers(current_user: User = Depends(get_current_user)):
    """
    Trigger scraping for all enabled companies.
    """
    from tasks.scraper_tasks import scrape_all_companies

    task = scrape_all_companies.delay()

    return TriggerResponse(
        status="dispatched",
        task_id=task.id,
        message="Dispatched scrape tasks for all companies",
    )


@router.post("/run-warning", response_model=TriggerResponse)
def trigger_warning_scrapers(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Trigger scraping for all warning scrapers (including stale ones).

    Warning scrapers are those with:
    - 2+ consecutive failures, OR
    - Last success more than 7 days ago

    This dispatches Celery tasks so it works for both HTTP and Playwright scrapers.
    """
    from datetime import timedelta
    from tasks.scraper_tasks import scrape_company_http, scrape_company_browser
    from scrapers.base import ScraperType

    slugs = ScraperRegistry.list_slugs()
    warning_slugs = []
    cutoff = datetime.utcnow() - timedelta(days=7)

    for slug in slugs:
        config = db.query(ScraperConfigDB).filter(
            ScraperConfigDB.company_slug == slug
        ).first()

        # Skip disabled scrapers
        if config and not config.is_enabled:
            continue

        is_warning = False

        if config:
            # Check consecutive failures
            if 2 <= (config.consecutive_failures or 0) < 5:
                is_warning = True
            # Check if stale (last success > 7 days ago)
            elif config.last_success_at and config.last_success_at < cutoff:
                is_warning = True
            elif not config.last_success_at:
                # Never succeeded - treat as warning if has been attempted
                if config.total_runs and config.total_runs > 0:
                    is_warning = True
        else:
            # No config means never run - check if it should run
            is_warning = True

        if is_warning:
            warning_slugs.append(slug)

    if not warning_slugs:
        return TriggerResponse(
            status="no_action",
            task_id=None,
            message="No warning scrapers found",
        )

    # Dispatch tasks based on scraper type
    http_count = 0
    browser_count = 0

    for slug in warning_slugs:
        scraper_cls = ScraperRegistry.get(slug)
        if not scraper_cls:
            continue

        if scraper_cls.config.scraper_type == ScraperType.HTTP:
            scrape_company_http.delay(slug)
            http_count += 1
        else:
            scrape_company_browser.delay(slug)
            browser_count += 1

    return TriggerResponse(
        status="dispatched",
        task_id=None,
        message=f"Dispatched {http_count} HTTP and {browser_count} browser scraper tasks for {len(warning_slugs)} warning scrapers",
    )


@router.post("/run-category/{category}", response_model=TriggerResponse)
def trigger_category(
    category: str,
    current_user: User = Depends(get_current_user)
):
    """
    Trigger scraping for all companies in a category.
    """
    if category not in ScraperRegistry.list_categories():
        raise HTTPException(status_code=404, detail="Category not found")

    from tasks.scraper_tasks import scrape_by_category

    task = scrape_by_category.delay(category)

    return TriggerResponse(
        status="dispatched",
        task_id=task.id,
        message=f"Dispatched scrape tasks for category: {category}",
    )


@router.patch("/{company_slug}/config")
def update_scraper_config(
    company_slug: str,
    update: ConfigUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Update scraper configuration.

    Allows enabling/disabling scrapers and setting config overrides.
    """
    scraper_cls = ScraperRegistry.get(company_slug)
    if not scraper_cls:
        raise HTTPException(status_code=404, detail="Scraper not found")

    config = db.query(ScraperConfigDB).filter(
        ScraperConfigDB.company_slug == company_slug
    ).first()

    if not config:
        config = ScraperConfigDB(company_slug=company_slug)
        db.add(config)

    if update.is_enabled is not None:
        config.is_enabled = update.is_enabled

    if update.config_overrides is not None:
        config.config_overrides = update.config_overrides

    db.commit()

    return {
        "company_slug": company_slug,
        "is_enabled": config.is_enabled,
        "config_overrides": config.config_overrides,
    }


@router.post("/{company_slug}/enable")
def enable_scraper(
    company_slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Enable a scraper."""
    return update_scraper_config(
        company_slug,
        ConfigUpdate(is_enabled=True),
        current_user,
        db,
    )


@router.post("/{company_slug}/disable")
def disable_scraper(
    company_slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disable a scraper."""
    return update_scraper_config(
        company_slug,
        ConfigUpdate(is_enabled=False),
        current_user,
        db,
    )


@router.get("/health/report")
def get_health_report(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get a health report for all scrapers.

    Groups scrapers by health status (healthy, warning, critical).
    """
    from tasks.maintenance_tasks import generate_scraper_health_report

    # Run synchronously for API response
    report = generate_scraper_health_report()
    return report


# ============== Custom Company Endpoints ==============

@router.post("/custom/detect", response_model=DetectBoardResponse)
async def detect_job_board(
    request: CustomCompanyRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Detect the job board type from a careers URL.

    Probes the URL to determine if it's Workday, Greenhouse, Lever, Ashby, etc.
    Returns job count if the API is valid.
    """
    from services.scraper_generator import scraper_generator

    board_type, api_info = await scraper_generator.detect_and_validate(request.careers_url)

    return DetectBoardResponse(
        board_type=board_type,
        valid=api_info.get('valid', False),
        job_count=api_info.get('job_count', 0),
        api_url=api_info.get('api_url'),
        error=api_info.get('error'),
    )


@router.post("/custom/add", response_model=CustomCompanyResponse)
async def add_custom_company(
    request: CustomCompanyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a custom company by detecting its job board and generating a scraper.

    1. Detects the job board type (Workday, Greenhouse, Lever, Ashby)
    2. Validates the API endpoint works
    3. Generates scraper code
    4. Registers the scraper
    5. Triggers initial scrape

    Returns the company slug and initial job count.
    """
    from services.scraper_generator import scraper_generator
    import re

    # Validate company name
    if not request.company_name or len(request.company_name) < 2:
        raise HTTPException(status_code=400, detail="Company name must be at least 2 characters")

    # Check if slug already exists
    slug = re.sub(r'[^a-z0-9]+', '', request.company_name.lower())
    if ScraperRegistry.get(slug):
        raise HTTPException(status_code=400, detail=f"Scraper for '{slug}' already exists")

    # Detect and validate
    board_type, api_info = await scraper_generator.detect_and_validate(request.careers_url)

    if board_type == 'unknown':
        raise HTTPException(
            status_code=400,
            detail=f"Could not detect job board type. Supported: Workday, Greenhouse, Lever, Ashby. Error: {api_info.get('error', 'Unknown')}"
        )

    if not api_info.get('valid'):
        raise HTTPException(
            status_code=400,
            detail=f"Could not validate API endpoint. Error: {api_info.get('error', 'API returned no jobs')}"
        )

    # Generate scraper
    try:
        slug, file_path = scraper_generator.generate_scraper(
            company_name=request.company_name,
            careers_url=request.careers_url,
            board_type=board_type,
            api_info=api_info,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate scraper: {str(e)}")

    # Reload scrapers to pick up new one
    scraper_generator.reload_scrapers()

    # Verify it's registered
    if not ScraperRegistry.get(slug):
        raise HTTPException(status_code=500, detail="Scraper generated but failed to register")

    # Trigger initial scrape
    task_id = None
    try:
        from tasks.scraper_tasks import scrape_company_http
        task = scrape_company_http.delay(slug)
        task_id = task.id
    except Exception as e:
        # Non-fatal - scraper was created, just couldn't trigger initial run
        pass

    return CustomCompanyResponse(
        status="success",
        slug=slug,
        company_name=request.company_name,
        board_type=board_type,
        job_count=api_info.get('job_count', 0),
        message=f"Scraper created for {request.company_name} ({board_type}). Found {api_info.get('job_count', 0)} jobs.",
        task_id=task_id,
    )


@router.delete("/custom/{company_slug}")
def delete_custom_scraper(
    company_slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete a custom scraper.

    Only allows deleting scrapers in the 'custom' category.
    """
    import os

    metadata = ScraperRegistry.get_metadata(company_slug)
    if not metadata:
        raise HTTPException(status_code=404, detail="Scraper not found")

    if metadata.get('category') != 'custom':
        raise HTTPException(status_code=400, detail="Can only delete custom scrapers")

    # Delete the scraper file
    scrapers_dir = os.path.dirname(os.path.dirname(__file__)) + '/scrapers/custom'
    file_path = os.path.join(scrapers_dir, f"{company_slug}.py")

    if os.path.exists(file_path):
        os.remove(file_path)

    # Delete from database
    db.query(ScraperRun).filter(ScraperRun.company_slug == company_slug).delete()
    db.query(ScraperConfigDB).filter(ScraperConfigDB.company_slug == company_slug).delete()
    db.commit()

    return {"status": "deleted", "slug": company_slug}


# ============== Synchronous Scraper Endpoints (No Celery) ==============

class SyncScrapeResponse(BaseModel):
    status: str
    company_slug: str
    jobs_found: int
    jobs_new: int
    jobs_updated: int
    duration_seconds: float
    error: Optional[str] = None


@router.post("/{company_slug}/run-sync", response_model=SyncScrapeResponse)
async def run_scraper_sync(
    company_slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Run a scraper synchronously without Celery.

    Use this when Celery workers are not available.
    Only HTTP scrapers are supported (browser scrapers require Celery).
    """
    import asyncio
    from datetime import datetime
    from scrapers.base import ScraperType
    from scrapers.rate_limiter import get_rate_limiter
    from services.scraper_service import save_scraped_jobs

    scraper_cls = ScraperRegistry.get(company_slug)
    if not scraper_cls:
        raise HTTPException(status_code=404, detail="Scraper not found")

    # Check scraper type
    scraper_config = scraper_cls.get_default_config()
    if scraper_config.scraper_type == ScraperType.BROWSER:
        raise HTTPException(
            status_code=400,
            detail="Browser scrapers require Celery. Use /run endpoint instead."
        )

    start_time = datetime.utcnow()

    try:
        # Create and run scraper
        rate_limiter = get_rate_limiter()
        scraper = scraper_cls(rate_limiter=rate_limiter)
        result = await scraper.run()

        jobs_new = 0
        jobs_updated = 0

        # Save jobs if successful
        if result.success and result.jobs:
            jobs_new, jobs_updated = save_scraped_jobs(db, company_slug, result.jobs)

        duration = (datetime.utcnow() - start_time).total_seconds()

        # Record the run
        from tasks.scraper_tasks import record_scraper_run
        result.jobs_new = jobs_new
        result.jobs_updated = jobs_updated
        record_scraper_run(db, company_slug, result)

        return SyncScrapeResponse(
            status="success" if result.success else "failed",
            company_slug=company_slug,
            jobs_found=result.jobs_found,
            jobs_new=jobs_new,
            jobs_updated=jobs_updated,
            duration_seconds=duration,
            error=result.error_message
        )

    except Exception as e:
        duration = (datetime.utcnow() - start_time).total_seconds()
        return SyncScrapeResponse(
            status="error",
            company_slug=company_slug,
            jobs_found=0,
            jobs_new=0,
            jobs_updated=0,
            duration_seconds=duration,
            error=str(e)
        )


@router.post("/run-warning-sync")
async def run_warning_scrapers_sync(
    limit: int = Query(default=100, ge=1, le=300, description="Max scrapers to run"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Run all warning HTTP scrapers synchronously without Celery.

    Warning scrapers are those with:
    - 2+ consecutive failures (but <5), OR
    - Last success more than 7 days ago

    Browser/Playwright scrapers are skipped (require Celery).
    """
    from datetime import timedelta
    from scrapers.base import ScraperType
    from scrapers.rate_limiter import get_rate_limiter
    from services.scraper_service import save_scraped_jobs
    from tasks.scraper_tasks import record_scraper_run

    slugs = ScraperRegistry.list_slugs()
    warning_slugs = []
    cutoff = datetime.utcnow() - timedelta(days=7)

    for slug in slugs:
        config = db.query(ScraperConfigDB).filter(
            ScraperConfigDB.company_slug == slug
        ).first()

        # Skip disabled scrapers
        if config and not config.is_enabled:
            continue

        is_warning = False

        if config:
            if 2 <= (config.consecutive_failures or 0) < 5:
                is_warning = True
            elif config.last_success_at and config.last_success_at < cutoff:
                is_warning = True
            elif not config.last_success_at and config.total_runs and config.total_runs > 0:
                is_warning = True
        else:
            is_warning = True

        if is_warning:
            warning_slugs.append(slug)

    # Filter to HTTP only and apply limit
    http_scrapers = []
    browser_skipped = 0

    for slug in warning_slugs:
        scraper_cls = ScraperRegistry.get(slug)
        if scraper_cls and scraper_cls.config.scraper_type == ScraperType.HTTP:
            http_scrapers.append(slug)
        else:
            browser_skipped += 1

    http_scrapers = http_scrapers[:limit]

    results = []
    total_jobs_found = 0
    total_jobs_new = 0

    rate_limiter = get_rate_limiter()

    for company_slug in http_scrapers:
        start_time = datetime.utcnow()

        try:
            scraper_cls = ScraperRegistry.get(company_slug)
            if not scraper_cls:
                continue

            scraper = scraper_cls(rate_limiter=rate_limiter)
            result = await scraper.run()

            jobs_new = 0
            jobs_updated = 0

            if result.success and result.jobs:
                jobs_new, jobs_updated = save_scraped_jobs(db, company_slug, result.jobs)
                result.jobs_new = jobs_new
                result.jobs_updated = jobs_updated

            record_scraper_run(db, company_slug, result)

            duration = (datetime.utcnow() - start_time).total_seconds()

            results.append({
                "company_slug": company_slug,
                "status": "success" if result.success else "failed",
                "jobs_found": result.jobs_found,
                "jobs_new": jobs_new,
                "duration_seconds": round(duration, 2),
                "error": result.error_message[:100] if result.error_message else None,
            })

            total_jobs_found += result.jobs_found
            total_jobs_new += jobs_new

        except Exception as e:
            results.append({
                "company_slug": company_slug,
                "status": "error",
                "error": str(e)[:100],
            })

    return {
        "status": "completed",
        "warning_scrapers_found": len(warning_slugs),
        "http_scrapers_run": len(results),
        "browser_scrapers_skipped": browser_skipped,
        "total_jobs_found": total_jobs_found,
        "total_jobs_new": total_jobs_new,
        "results": results
    }


@router.post("/run-all-sync")
async def run_all_scrapers_sync(
    limit: int = Query(default=50, ge=1, le=200, description="Max scrapers to run"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Run all HTTP scrapers synchronously without Celery.

    Processes scrapers sequentially. Limited to HTTP scrapers only.
    Use limit parameter to control how many scrapers to run.
    """
    from datetime import datetime
    from scrapers.base import ScraperType
    from scrapers.rate_limiter import get_rate_limiter
    from services.scraper_service import save_scraped_jobs
    from tasks.scraper_tasks import record_scraper_run

    all_scrapers = list_all_scrapers()
    http_scrapers = [
        s for s in all_scrapers
        if s.get('scraper_type') == 'http'
    ][:limit]

    results = []
    total_jobs_found = 0
    total_jobs_new = 0

    rate_limiter = get_rate_limiter()

    for scraper_info in http_scrapers:
        company_slug = scraper_info['slug']
        start_time = datetime.utcnow()

        try:
            scraper_cls = ScraperRegistry.get(company_slug)
            if not scraper_cls:
                continue

            scraper = scraper_cls(rate_limiter=rate_limiter)
            result = await scraper.run()

            jobs_new = 0
            jobs_updated = 0

            if result.success and result.jobs:
                jobs_new, jobs_updated = save_scraped_jobs(db, company_slug, result.jobs)
                result.jobs_new = jobs_new
                result.jobs_updated = jobs_updated

            record_scraper_run(db, company_slug, result)

            duration = (datetime.utcnow() - start_time).total_seconds()

            results.append({
                "company_slug": company_slug,
                "status": "success" if result.success else "failed",
                "jobs_found": result.jobs_found,
                "jobs_new": jobs_new,
                "duration_seconds": round(duration, 2),
            })

            total_jobs_found += result.jobs_found
            total_jobs_new += jobs_new

        except Exception as e:
            results.append({
                "company_slug": company_slug,
                "status": "error",
                "error": str(e)[:100],
            })

    return {
        "status": "completed",
        "scrapers_run": len(results),
        "total_jobs_found": total_jobs_found,
        "total_jobs_new": total_jobs_new,
        "results": results
    }


# ============== Webhook Trigger (No Auth) ==============

@router.post("/webhook/trigger")
async def webhook_trigger_scrapers(
    secret: str = Query(..., description="Webhook secret key"),
):
    """
    Trigger scrapers via webhook. Requires secret key.
    Use this for external triggers (e.g., cron jobs, CI/CD).
    """
    import os
    expected_secret = os.environ.get("SCRAPER_WEBHOOK_SECRET", "cariara-scrape-2024")

    if secret != expected_secret:
        raise HTTPException(status_code=403, detail="Invalid secret")

    try:
        from tasks.scraper_tasks import scrape_all_companies
        task = scrape_all_companies.delay()
        return {
            "status": "dispatched",
            "task_id": task.id,
            "message": "Scraper tasks dispatched via webhook"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to dispatch: {str(e)}")


# ============== Scraper Maintenance Endpoints ==============

@router.post("/maintenance/reset-failures")
def reset_all_failure_counts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Reset failure counts for all scrapers.
    Use this after fixing scraper issues to give them a fresh start.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    updated = db.query(ScraperConfigDB).filter(
        ScraperConfigDB.consecutive_failures > 0
    ).update({"consecutive_failures": 0})

    db.commit()

    return {
        "status": "success",
        "scrapers_reset": updated,
        "message": f"Reset failure counts for {updated} scrapers"
    }


@router.post("/maintenance/disable-critical")
def disable_critical_scrapers(
    threshold: int = Query(default=10, ge=5, description="Failure threshold to consider critical"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Disable all scrapers with consecutive failures above threshold.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Get critical scrapers
    critical = db.query(ScraperConfigDB).filter(
        ScraperConfigDB.consecutive_failures >= threshold
    ).all()

    disabled_slugs = []
    for config in critical:
        config.is_enabled = False
        disabled_slugs.append(config.company_slug)

    db.commit()

    return {
        "status": "success",
        "disabled_count": len(disabled_slugs),
        "disabled_scrapers": disabled_slugs[:50],  # Show first 50
        "message": f"Disabled {len(disabled_slugs)} scrapers with {threshold}+ failures"
    }


@router.post("/{company_slug}/reset-failures")
def reset_scraper_failures(
    company_slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Reset failure count for a specific scraper."""
    config = db.query(ScraperConfigDB).filter(
        ScraperConfigDB.company_slug == company_slug
    ).first()

    if not config:
        # Create new config with zero failures
        config = ScraperConfigDB(
            company_slug=company_slug,
            consecutive_failures=0,
            is_enabled=True
        )
        db.add(config)
    else:
        config.consecutive_failures = 0
        config.is_enabled = True

    db.commit()

    return {
        "status": "success",
        "company_slug": company_slug,
        "message": f"Reset failures for {company_slug}"
    }


@router.get("/maintenance/summary")
def get_maintenance_summary(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get a summary of scraper health for maintenance purposes."""
    from sqlalchemy import func

    # Get counts by failure level
    configs = db.query(ScraperConfigDB).all()

    critical = [c for c in configs if c.consecutive_failures >= 5]
    warning = [c for c in configs if 2 <= c.consecutive_failures < 5]
    disabled = [c for c in configs if not c.is_enabled]

    # Get scrapers that have never succeeded
    never_succeeded = [c for c in configs if c.last_success_at is None and c.consecutive_failures > 0]

    return {
        "total_configured": len(configs),
        "critical_count": len(critical),
        "warning_count": len(warning),
        "disabled_count": len(disabled),
        "never_succeeded_count": len(never_succeeded),
        "critical_scrapers": [{"slug": c.company_slug, "failures": c.consecutive_failures} for c in critical[:20]],
        "never_succeeded": [{"slug": c.company_slug, "failures": c.consecutive_failures} for c in never_succeeded[:20]],
    }
