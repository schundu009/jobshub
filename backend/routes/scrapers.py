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

import logging
import os
import re
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from database import get_db
from models import JobBoard, ScraperRun, ScraperConfigDB, User
from scrapers.registry import ScraperRegistry, list_all_scrapers
from services.scraper_service import get_scraper_stats, get_all_scraper_stats
from services.redis_service import redis_service
from utils.security import validate_url_ssrf_safe
from middleware.auth import get_current_admin

logger = logging.getLogger(__name__)

# Every endpoint except the secret-protected webhooks is admin-only
# (Depends(get_current_admin) per route; the webhooks carry their own secret).
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
    last_error_type: Optional[str] = None  # save_failed, empty_result, timeout, ...
    last_run_success: Optional[bool] = None
    last_run_jobs_found: Optional[int] = None
    last_run_note: Optional[str] = None  # latest run's message, e.g. "saved: 0 new, 0 updated, 21 skipped_old"
    active_jobs: int
    total_jobs: int
    # Scrapers switched off in code (ScraperConfig(enabled=False)) are listed
    # too, with is_enabled=False and the reason, so they don't silently vanish.
    disabled_reason: Optional[str] = None
    has_scraper: bool = True


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
    task_id: Optional[str] = None
    message: str
    count: Optional[int] = None
    queued: Optional[int] = None


class ConfigUpdate(BaseModel):
    is_enabled: Optional[bool] = None
    config_overrides: Optional[dict] = None


class DetectBoardRequest(BaseModel):
    careers_url: str = Field(..., min_length=10, max_length=500)

    @field_validator('careers_url')
    @classmethod
    def validate_url(cls, v):
        is_valid, error = validate_url_ssrf_safe(v)
        if not is_valid:
            raise ValueError(error)
        return v


class CustomCompanyRequest(DetectBoardRequest):
    company_name: str = Field(..., min_length=2, max_length=255)


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


# ============== Webhook Trigger (No Auth) ==============
# Registered before the /{company_slug}/... routes: otherwise
# POST /webhook/run-sync matches /{company_slug}/run-sync (slug "webhook").

def _check_webhook_secret(secret: str) -> None:
    """
    Webhooks are authenticated by SCRAPER_WEBHOOK_SECRET only. There is no
    default: with the env var unset the webhooks are disabled (503).
    """
    expected = os.environ.get("SCRAPER_WEBHOOK_SECRET", "")
    if not expected:
        raise HTTPException(status_code=503, detail="webhook disabled")
    if not secrets.compare_digest(secret or "", expected):
        raise HTTPException(status_code=403, detail="Invalid secret")


@router.post("/webhook/trigger")
def webhook_trigger_scrapers(
    secret: str = Query(..., description="Webhook secret key"),
):
    """
    Trigger scrapers via webhook. Requires secret key.
    Use this for external triggers (e.g., cron jobs, CI/CD).
    """
    _check_webhook_secret(secret)

    try:
        from tasks.scraper_tasks import scrape_all_companies
        # force=True: an explicit external trigger bypasses the interval gate.
        task = scrape_all_companies.apply_async(kwargs={"force": True}, queue="scrapers_orchestrator")
        return {
            "status": "dispatched",
            "task_id": task.id,
            "message": "Scraper tasks dispatched via webhook"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to dispatch: {str(e)}")


# ============== Endpoints ==============

@router.get("/", response_model=list[ScraperInfo])
def list_scrapers(
    category: Optional[str] = Query(None, description="Filter by category"),
    scraper_type: Optional[str] = Query(None, description="Filter by type (http, playwright)"),
    current_user: User = Depends(get_current_admin),
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


SCRAPER_STATUS_CACHE_KEY = "scrapers:status"
SCRAPER_STATUS_CACHE_TTL = 60  # seconds


@router.get("/status", response_model=list[ScraperStatus])
def get_all_status(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Get status of all scrapers.

    Returns health metrics for each scraper. Computed with a fixed number of
    grouped queries (not per scraper) and cached in Redis for 60s.
    """
    cached = redis_service.cache_get(SCRAPER_STATUS_CACHE_KEY)
    if cached is not None:
        return cached

    slugs = ScraperRegistry.list_slugs() + ScraperRegistry.list_board_slugs()
    statuses = [
        ScraperStatus(**stats).model_dump()
        for stats in get_all_scraper_stats(db, slugs)
    ]

    enabled_slugs = set(slugs)
    disabled = {
        slug: info for slug, info in ScraperRegistry.get_disabled().items()
        if slug not in enabled_slugs
    }
    if disabled:
        disabled_stats = get_all_scraper_stats(
            db, list(disabled), names={slug: info.get("company_name") or slug for slug, info in disabled.items()}
        )
        for stats in disabled_stats:
            stats["is_enabled"] = False
            stats["disabled_reason"] = disabled[stats["company_slug"]].get("reason") or "disabled in code"
            statuses.append(ScraperStatus(**stats).model_dump())

    redis_service.cache_set(SCRAPER_STATUS_CACHE_KEY, statuses, SCRAPER_STATUS_CACHE_TTL)
    return statuses


@router.get("/health")
def get_scraper_health(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Per-board freshness from scraper_runs: boards with no success in 48h
    (stale), boards failing 3+ runs in a row (failing), and counts by ATS.
    """
    from services.scraper_health import health_report
    return health_report(db)


@router.get("/{company_slug}")
def get_scraper_detail(
    company_slug: str,
    current_user: User = Depends(get_current_admin),
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
    current_user: User = Depends(get_current_admin),
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
    current_user: User = Depends(get_current_admin),
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


def _warning_slugs(db: Session) -> list[str]:
    """
    Enabled scrapers in "warning" state (same rules as the admin UI):
    2-4 consecutive failures, last success > 7 days ago, or runs but never a
    success. Scrapers that have never run count too. One query for all configs.
    """
    cutoff = datetime.utcnow() - timedelta(days=7)
    configs = {c.company_slug: c for c in db.query(ScraperConfigDB).all()}
    warning = []
    for slug in ScraperRegistry.list_slugs() + ScraperRegistry.list_board_slugs():
        config = configs.get(slug)
        if config is None:
            warning.append(slug)
            continue
        if not config.is_enabled:
            continue
        if 2 <= (config.consecutive_failures or 0) < 5:
            warning.append(slug)
        elif config.last_success_at and config.last_success_at < cutoff:
            warning.append(slug)
        elif not config.last_success_at and (config.total_runs or 0) > 0:
            warning.append(slug)
    return warning


def _dispatch_scrape(slug: str):
    """Queue one scraper on the Celery queue that matches its type. Returns the AsyncResult."""
    from tasks.scraper_tasks import scrape_company_http, scrape_company_browser
    from scrapers.base import ScraperType

    scraper_cls = ScraperRegistry.get(slug)
    if scraper_cls.config.scraper_type == ScraperType.HTTP:
        return scrape_company_http.apply_async(args=[slug], queue="scrapers_http")
    return scrape_company_browser.apply_async(args=[slug], queue="scrapers_browser")


def _dispatch_many(slugs: list[str]) -> tuple[int, int]:
    """Queue many scrapers; returns (http_count, browser_count). Raises 503 if Celery is unreachable."""
    from scrapers.base import ScraperType

    http_count = browser_count = 0
    try:
        for slug in slugs:
            scraper_cls = ScraperRegistry.get(slug)
            if not scraper_cls:
                continue
            _dispatch_scrape(slug)
            if scraper_cls.config.scraper_type == ScraperType.HTTP:
                http_count += 1
            else:
                browser_count += 1
    except Exception as e:
        logger.exception("Failed to queue scraper tasks")
        raise HTTPException(
            status_code=503,
            detail=f"Could not queue scraper tasks (Celery/Redis unavailable): {str(e)[:200]}",
        )
    return http_count, browser_count


@router.post("/run-warning", response_model=TriggerResponse)
def trigger_warning_scrapers(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Queue a scrape for every warning scraper (including stale ones).

    Warning scrapers are those with:
    - 2+ consecutive failures, OR
    - Last success more than 7 days ago

    This dispatches Celery tasks so it works for both HTTP and Playwright scrapers.
    """
    warning_slugs = _warning_slugs(db)
    if not warning_slugs:
        return TriggerResponse(
            status="no_action",
            message="No warning scrapers found",
            count=0,
            queued=0,
        )

    http_count, browser_count = _dispatch_many(warning_slugs)
    queued = http_count + browser_count
    return TriggerResponse(
        status="queued",
        message=f"Queued {queued} warning scrapers ({http_count} HTTP, {browser_count} browser)",
        count=len(warning_slugs),
        queued=queued,
    )


@router.patch("/{company_slug}/config")
def update_scraper_config(
    company_slug: str,
    update: ConfigUpdate,
    current_user: User = Depends(get_current_admin),
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
        if update.is_enabled and not config.is_enabled:
            # Fresh start: otherwise the old streak makes auto_heal switch it
            # straight back off (it disables at 10+ consecutive failures).
            config.consecutive_failures = 0
            overrides = dict(config.config_overrides or {})
            overrides.pop("auto_disabled", None)
            overrides.pop("auto_disabled_reason", None)
            config.config_overrides = overrides
        config.is_enabled = update.is_enabled

    if update.config_overrides is not None:
        config.config_overrides = update.config_overrides

    db.commit()
    redis_service.cache_delete(SCRAPER_STATUS_CACHE_KEY)

    return {
        "company_slug": company_slug,
        "is_enabled": config.is_enabled,
        "config_overrides": config.config_overrides,
    }


@router.post("/{company_slug}/enable")
def enable_scraper(
    company_slug: str,
    current_user: User = Depends(get_current_admin),
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
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Disable a scraper."""
    return update_scraper_config(
        company_slug,
        ConfigUpdate(is_enabled=False),
        current_user,
        db,
    )


# ============== Custom Company Endpoints ==============

@router.post("/custom/detect", response_model=DetectBoardResponse)
async def detect_job_board(
    request: DetectBoardRequest,
    current_user: User = Depends(get_current_admin)
):
    """
    Detect the ATS board behind a careers URL (services.ats_detect): Greenhouse,
    Lever, Ashby, SmartRecruiters or Workday, confirmed by its API listing jobs.
    """
    from services import ats_detect

    found = await run_in_threadpool(ats_detect.detect, request.careers_url)
    if not found:
        return DetectBoardResponse(
            board_type="unknown", valid=False, job_count=0, api_url=None,
            error="No Greenhouse, Lever, Ashby, SmartRecruiters or Workday board with jobs found",
        )
    return DetectBoardResponse(
        board_type=found["ats"], valid=True, job_count=found["job_count"],
        api_url=found["api_url"], error=None,
    )


def _board_slug(company_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", company_name.lower())


@router.post("/custom/add", response_model=CustomCompanyResponse)
async def add_custom_company(
    request: CustomCompanyRequest,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Add a company as data: detect its ATS board and save a job_boards row.
    The registry builds its scraper from the row (scrapers.board_scraper), so
    it survives redeploys and every worker sees it.

    400 when no supported board with jobs is found; 409 when the slug, or the
    board itself, already has a scraper. Queues a first scrape.
    """
    from services import ats_detect

    company_name = request.company_name.strip()
    slug = _board_slug(company_name)
    if not slug or not slug[0].isalpha():
        raise HTTPException(status_code=400, detail="Company name must start with a letter")
    if ScraperRegistry.has_coded(slug) or db.query(JobBoard).filter(JobBoard.slug == slug).first():
        raise HTTPException(status_code=409, detail=f"Scraper for '{slug}' already exists")

    found = await run_in_threadpool(ats_detect.detect, request.careers_url)
    if not found:
        raise HTTPException(
            status_code=400,
            detail="Could not detect a job board with jobs. Supported: Greenhouse, Lever, Ashby, SmartRecruiters, Workday",
        )

    # The same board under another name would be scraped twice.
    duplicate = db.query(JobBoard).filter(JobBoard.ats == found["ats"], JobBoard.board == found["board"]).first()
    owner = duplicate.slug if duplicate else next(
        (s for s, cls in ScraperRegistry.get_all().items() if getattr(cls, "API_URL", None) == found["api_url"]),
        None,
    )
    if owner:
        raise HTTPException(status_code=409, detail=f"This board is already scraped as '{owner}'")

    db.add(JobBoard(
        company_name=company_name, slug=slug, ats=found["ats"], board=found["board"],
        careers_url=request.careers_url, enabled=True,
    ))
    db.commit()
    redis_service.cache_delete(SCRAPER_STATUS_CACHE_KEY)

    task_id = None
    try:
        from tasks.scraper_tasks import scrape_company_http
        task_id = scrape_company_http.apply_async(args=[slug], queue="scrapers_http").id
    except Exception as e:
        # Non-fatal: the board is saved and the next scheduled run picks it up.
        logger.warning(f"Could not queue the first scrape of {slug}: {e}")

    return CustomCompanyResponse(
        status="success",
        slug=slug,
        company_name=company_name,
        board_type=found["ats"],
        job_count=found["job_count"],
        message=f"Board added for {company_name} ({found['ats']}). Found {found['job_count']} jobs.",
        task_id=task_id,
    )


@router.delete("/custom/{company_slug}")
def delete_custom_scraper(
    company_slug: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Delete a company added from the admin (its job_boards row) and its run
    history. Coded scrapers can't be deleted here.
    """
    board = db.query(JobBoard).filter(JobBoard.slug == company_slug).first()
    if not board:
        if ScraperRegistry.has_coded(company_slug):
            raise HTTPException(status_code=400, detail="Only companies added from the admin can be deleted")
        raise HTTPException(status_code=404, detail="Scraper not found")

    db.delete(board)
    db.query(ScraperRun).filter(ScraperRun.company_slug == company_slug).delete()
    db.query(ScraperConfigDB).filter(ScraperConfigDB.company_slug == company_slug).delete()
    db.commit()
    redis_service.cache_delete(SCRAPER_STATUS_CACHE_KEY)

    return {"status": "deleted", "slug": company_slug}


class RedetectRequest(BaseModel):
    careers_url: Optional[str] = Field(default=None, min_length=10, max_length=500)

    @field_validator('careers_url')
    @classmethod
    def validate_url(cls, v):
        if v is None:
            return v
        is_valid, error = validate_url_ssrf_safe(v)
        if not is_valid:
            raise ValueError(error)
        return v


def _find_moved_board(board: "JobBoard", careers_url: Optional[str]) -> Optional[dict]:
    """
    Where a company's board is now: the careers page (given, else saved), then
    the same board token on every other supported ATS (companies that switch
    ATS usually keep their name as the token).
    """
    from services import ats_detect

    url = careers_url or board.careers_url
    if url:
        found = ats_detect.detect(url)
        if found:
            return found
    for ats in ats_detect.SUPPORTED_ATS:
        if ats == board.ats or ats == "workday":
            continue
        count = ats_detect.probe(ats, board.board)
        if count > 0:
            return {"ats": ats, "board": board.board, "api_url": ats_detect.api_url(ats, board.board), "job_count": count}
    return None


@router.post("/custom/{company_slug}/redetect")
async def redetect_job_board(
    company_slug: str,
    request: Optional[RedetectRequest] = None,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    """
    Point a failing board at the company's current ATS board (a company that
    moved from Lever to Ashby, say): update the job_boards row, clear the
    failure streak, re-enable it and queue a scrape. 400 when no board with
    jobs is found; 409 when that board is already scraped under another slug.
    """
    board = db.query(JobBoard).filter(JobBoard.slug == company_slug).first()
    if not board:
        if ScraperRegistry.has_coded(company_slug):
            raise HTTPException(status_code=400, detail="Only companies added as boards can be re-detected")
        raise HTTPException(status_code=404, detail="Scraper not found")

    careers_url = request.careers_url if request else None
    found = await run_in_threadpool(_find_moved_board, board, careers_url)
    if not found:
        raise HTTPException(status_code=400, detail="No current job board with jobs was found")

    other = db.query(JobBoard).filter(
        JobBoard.ats == found["ats"], JobBoard.board == found["board"], JobBoard.slug != company_slug
    ).first()
    if other:
        raise HTTPException(status_code=409, detail=f"This board is already scraped as '{other.slug}'")

    previous = {"ats": board.ats, "board": board.board}
    board.ats, board.board = found["ats"], found["board"]
    if careers_url:
        board.careers_url = careers_url
    board.enabled = True

    config = db.query(ScraperConfigDB).filter(ScraperConfigDB.company_slug == company_slug).first()
    if config:
        config.is_enabled = True
        config.consecutive_failures = 0
        overrides = dict(config.config_overrides or {})
        overrides.pop("auto_disabled", None)
        overrides.pop("auto_disabled_reason", None)
        config.config_overrides = overrides
    db.commit()
    redis_service.cache_delete(SCRAPER_STATUS_CACHE_KEY)

    task_id = None
    try:
        from tasks.scraper_tasks import scrape_company_http
        task_id = scrape_company_http.apply_async(args=[company_slug], queue="scrapers_http").id
    except Exception as e:
        logger.warning(f"Could not queue a scrape of {company_slug} after re-detect: {e}")

    return {
        "status": "updated",
        "slug": company_slug,
        "previous": previous,
        "ats": found["ats"],
        "board": found["board"],
        "job_count": found["job_count"],
        "task_id": task_id,
        "message": f"{board.company_name}: {previous['ats']} → {found['ats']} ({found['job_count']} jobs)",
    }


# ============== Synchronous Scraper Endpoints (No Celery) ==============

class SyncScrapeResponse(BaseModel):
    status: str  # success | failed | queued
    company_slug: str
    jobs_found: int
    jobs_new: int
    jobs_updated: int
    duration_seconds: float
    error: Optional[str] = None
    task_id: Optional[str] = None


@router.post("/{company_slug}/run-sync", response_model=SyncScrapeResponse)
async def run_scraper_sync(
    company_slug: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Run one scraper now and return its result.

    HTTP scrapers run in-process (the blocking DB writes go to the threadpool).
    Playwright scrapers need a browser, so they are queued on Celery instead and
    the response has status "queued". Failures come back as status "failed"
    with an error message rather than a 500.
    """
    from scrapers.base import ScraperType

    scraper_cls = ScraperRegistry.get(company_slug)
    if not scraper_cls:
        raise HTTPException(status_code=404, detail="Scraper not found")

    start_time = datetime.utcnow()

    def _response(status: str, error: Optional[str] = None, result=None, task_id=None) -> SyncScrapeResponse:
        return SyncScrapeResponse(
            status=status,
            company_slug=company_slug,
            jobs_found=result.jobs_found if result else 0,
            jobs_new=result.jobs_new if result else 0,
            jobs_updated=result.jobs_updated if result else 0,
            duration_seconds=(datetime.utcnow() - start_time).total_seconds(),
            error=error,
            task_id=task_id,
        )

    try:
        if scraper_cls.config.scraper_type != ScraperType.HTTP:
            task = _dispatch_scrape(company_slug)
            return _response("queued", task_id=task.id)

        from scrapers.rate_limiter import get_rate_limiter
        from tasks.scraper_tasks import record_scraper_run, save_jobs_into_result

        scraper = scraper_cls(rate_limiter=get_rate_limiter())
        result = await scraper.run()

        if result.success and result.jobs:
            await run_in_threadpool(save_jobs_into_result, db, company_slug, result)

        await run_in_threadpool(record_scraper_run, db, company_slug, result)
        redis_service.cache_delete(SCRAPER_STATUS_CACHE_KEY)

        return _response(
            "success" if result.success else "failed",
            error=result.error_message,
            result=result,
        )

    except Exception as e:
        logger.exception(f"run-sync failed for {company_slug}")
        try:
            db.rollback()
        except Exception:
            pass
        return _response("failed", error=str(e)[:500])


# ============== Scraper Maintenance Endpoints ==============

@router.post("/{company_slug}/reset-failures")
def reset_scraper_failures(
    company_slug: str,
    current_user: User = Depends(get_current_admin),
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
    redis_service.cache_delete(SCRAPER_STATUS_CACHE_KEY)

    return {
        "status": "success",
        "company_slug": company_slug,
        "message": f"Reset failures for {company_slug}"
    }

