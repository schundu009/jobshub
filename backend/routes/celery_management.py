"""
Celery Management API Routes.

Endpoints for:
- Viewing worker and queue status
- Triggering tasks manually
- Managing schedules
- Viewing task history
"""

from datetime import datetime, timedelta
from typing import Optional, List
import json

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import User, AppSetting, ScraperRun
from middleware.auth import get_current_user, get_current_user_detached
from config import settings
from services.redis_service import redis_service

router = APIRouter(prefix="/api/celery", tags=["celery"])


# ============== Pydantic Models ==============

class WorkerInfo(BaseModel):
    hostname: str
    status: str
    active_tasks: int
    processed: int
    concurrency: int
    queues: List[str]


class QueueInfo(BaseModel):
    name: str
    messages: int
    consumers: int


class CeleryStatus(BaseModel):
    connected: bool
    workers: List[WorkerInfo]
    queues: List[QueueInfo]
    redis_connected: bool


class TaskInfo(BaseModel):
    task_id: str
    name: str
    status: str
    args: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    error: Optional[str] = None


class ScheduleItem(BaseModel):
    name: str
    task: str
    schedule: str
    enabled: bool
    last_run: Optional[str] = None
    next_run: Optional[str] = None


class ScheduleUpdate(BaseModel):
    scraper_interval_hours: int = Field(ge=1, le=24, default=6)
    auto_apply_enabled: bool = True
    description_fetch_enabled: bool = True


class TriggerTaskRequest(BaseModel):
    task_name: str
    args: Optional[List] = None
    kwargs: Optional[dict] = None


class TriggerResponse(BaseModel):
    status: str
    task_id: Optional[str] = None
    message: str


# ============== Helper Functions ==============

def get_celery_app():
    """Get the Celery app instance."""
    from celery_app import celery_app
    return celery_app


def get_redis_client():
    """Shared Redis client (pooled, 1s socket timeouts, circuit breaker)."""
    try:
        return redis_service.client
    except Exception:
        return None


CELERY_STATUS_CACHE_KEY = "celery:status"
CELERY_SCHEDULES_CACHE_KEY = "celery:schedules"
CELERY_CACHE_TTL = 20  # seconds
INSPECT_TIMEOUT = 1.0  # seconds per broadcast


def _collect_celery_status() -> CeleryStatus:
    """Inspect workers + queue depths. No DB access (runs outside any session)."""
    celery_app = get_celery_app()
    workers = []
    queues = []

    redis_connected = redis_service.ping()

    # Get worker information. `stats` is the only broadcast that has to wait
    # the full timeout (unknown number of replies). The follow-up calls are
    # addressed to the known workers with limit=N, so they return as soon as
    # every worker has replied. No workers -> skip them entirely.
    broker_is_redis = (settings.celery_broker_url or "") == settings.redis_url
    try:
        if broker_is_redis and not redis_connected:
            # Broker unreachable: a broadcast would just block on reconnects.
            raise ConnectionError("Celery broker (Redis) unreachable")
        stats = celery_app.control.inspect(timeout=INSPECT_TIMEOUT).stats() or {}
        active = {}
        active_queues = {}
        if stats:
            hosts = list(stats.keys())
            targeted = celery_app.control.inspect(
                destination=hosts, timeout=INSPECT_TIMEOUT, limit=len(hosts)
            )
            active = targeted.active() or {}
            active_queues = targeted.active_queues() or {}

        for hostname, worker_stats in stats.items():
            worker_queues = []
            if hostname in active_queues:
                worker_queues = [q.get('name', '') for q in active_queues[hostname]]

            workers.append(WorkerInfo(
                hostname=hostname,
                status="online",
                active_tasks=len(active.get(hostname, [])),
                processed=worker_stats.get('total', {}).get('tasks.scraper_tasks.scrape_company_http', 0) +
                          worker_stats.get('total', {}).get('tasks.scraper_tasks.scrape_company_browser', 0),
                concurrency=worker_stats.get('pool', {}).get('max-concurrency', 0),
                queues=worker_queues,
            ))
    except Exception:
        # Workers not reachable
        pass

    # Get queue information from Redis (one pipelined round-trip)
    if redis_connected:
        queue_names = ['default', 'scrapers_http', 'scrapers_browser', 'scrapers_orchestrator', 'maintenance']
        try:
            pipe = redis_service.client.pipeline(transaction=False)
            for queue_name in queue_names:
                pipe.llen(queue_name)
            lengths = pipe.execute(raise_on_error=False)
        except Exception:
            lengths = [0] * len(queue_names)
        for queue_name, messages in zip(queue_names, lengths):
            queues.append(QueueInfo(
                name=queue_name,
                messages=messages if isinstance(messages, int) else 0,
                consumers=len([w for w in workers if queue_name in w.queues]),
            ))

    return CeleryStatus(
        connected=len(workers) > 0,
        workers=workers,
        queues=queues,
        redis_connected=redis_connected,
    )


# ============== Endpoints ==============

@router.get("/status", response_model=CeleryStatus)
def get_celery_status(current_user: User = Depends(get_current_user_detached)):
    """
    Get Celery worker and queue status.

    Returns information about connected workers and queue depths.
    Cached in Redis for 20s; the auth dependency releases its DB connection
    before the (slow) worker broadcast runs.
    """
    cached = redis_service.cache_get(CELERY_STATUS_CACHE_KEY)
    if cached:
        return cached

    status = _collect_celery_status()
    redis_service.cache_set(CELERY_STATUS_CACHE_KEY, status.model_dump(), CELERY_CACHE_TTL)
    return status


@router.get("/schedules", response_model=List[ScheduleItem])
def get_schedules(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get configured task schedules. Cached in Redis for 20s.
    """
    cached = redis_service.cache_get(CELERY_SCHEDULES_CACHE_KEY)
    if cached is not None:
        return cached

    celery_app = get_celery_app()
    schedules = []

    # Get schedule configuration from database
    interval_setting = db.query(AppSetting).filter(
        AppSetting.key == "scraper_interval_hours"
    ).first()
    interval_hours = int(interval_setting.value) if interval_setting else settings.scraper_schedule_hours

    auto_apply_setting = db.query(AppSetting).filter(
        AppSetting.key == "auto_apply_enabled"
    ).first()
    auto_apply_enabled = auto_apply_setting.value.lower() == "true" if auto_apply_setting else True

    desc_fetch_setting = db.query(AppSetting).filter(
        AppSetting.key == "description_fetch_enabled"
    ).first()
    desc_fetch_enabled = desc_fetch_setting.value.lower() == "true" if desc_fetch_setting else True

    # Build schedule list from beat_schedule
    beat_schedule = celery_app.conf.beat_schedule

    for name, config in beat_schedule.items():
        task = config.get('task', '')
        schedule = config.get('schedule')

        # Format schedule for display
        schedule_str = str(schedule)
        if hasattr(schedule, 'minute') and hasattr(schedule, 'hour'):
            hour = schedule.hour if schedule.hour != '*' else '*'
            minute = schedule.minute if schedule.minute != '*' else '*'
            schedule_str = f"cron({minute} {hour} * * *)"

        # Determine if enabled based on settings
        enabled = True
        if 'auto_apply' in name.lower() or 'application' in name.lower():
            enabled = auto_apply_enabled
        elif 'description' in name.lower():
            enabled = desc_fetch_enabled

        schedules.append(ScheduleItem(
            name=name,
            task=task,
            schedule=schedule_str,
            enabled=enabled,
            last_run=None,  # Would need to track this separately
            next_run=None,
        ))

    redis_service.cache_set(
        CELERY_SCHEDULES_CACHE_KEY, [item.model_dump() for item in schedules], CELERY_CACHE_TTL
    )
    return schedules


@router.put("/schedules")
def update_schedules(
    update: ScheduleUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update task schedules.

    Note: Schedule changes take effect on next Celery Beat restart.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    # Update scraper interval
    interval_setting = db.query(AppSetting).filter(
        AppSetting.key == "scraper_interval_hours"
    ).first()
    if interval_setting:
        interval_setting.value = str(update.scraper_interval_hours)
    else:
        db.add(AppSetting(key="scraper_interval_hours", value=str(update.scraper_interval_hours)))

    # Update auto-apply enabled
    auto_apply_setting = db.query(AppSetting).filter(
        AppSetting.key == "auto_apply_enabled"
    ).first()
    if auto_apply_setting:
        auto_apply_setting.value = str(update.auto_apply_enabled).lower()
    else:
        db.add(AppSetting(key="auto_apply_enabled", value=str(update.auto_apply_enabled).lower()))

    # Update description fetch enabled
    desc_fetch_setting = db.query(AppSetting).filter(
        AppSetting.key == "description_fetch_enabled"
    ).first()
    if desc_fetch_setting:
        desc_fetch_setting.value = str(update.description_fetch_enabled).lower()
    else:
        db.add(AppSetting(key="description_fetch_enabled", value=str(update.description_fetch_enabled).lower()))

    db.commit()
    redis_service.cache_delete(CELERY_SCHEDULES_CACHE_KEY)

    return {
        "status": "success",
        "message": "Schedules updated. Restart Celery Beat for changes to take effect.",
        "settings": {
            "scraper_interval_hours": update.scraper_interval_hours,
            "auto_apply_enabled": update.auto_apply_enabled,
            "description_fetch_enabled": update.description_fetch_enabled,
        }
    }


@router.get("/tasks/recent", response_model=List[TaskInfo])
def get_recent_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get recent task executions from scraper runs.
    """
    # Get recent scraper runs as proxy for task history
    runs = db.query(ScraperRun).order_by(
        ScraperRun.run_at.desc()
    ).limit(limit).all()

    tasks = []
    for run in runs:
        tasks.append(TaskInfo(
            task_id=run.celery_task_id or f"run-{run.id}",
            name=f"scrape_company ({run.company_slug})",
            status="SUCCESS" if run.success else "FAILURE",
            args=run.company_slug,
            started_at=run.started_at.isoformat() if run.started_at else None,
            completed_at=run.completed_at.isoformat() if run.completed_at else run.run_at.isoformat() if run.run_at else None,
            result=f"{run.jobs_found} jobs found, {run.jobs_new or 0} new" if run.success else None,
            error=run.error_message if not run.success else None,
        ))

    return tasks


@router.post("/tasks/trigger", response_model=TriggerResponse)
def trigger_task(
    request: TriggerTaskRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Manually trigger a Celery task.

    Available tasks:
    - scrape_all_companies: Run all scrapers
    - scrape_by_category: Run scrapers for a category (args: ["big_tech"])
    - cleanup_old_scraper_runs: Clean up old run records
    - mark_stale_jobs_inactive: Mark old jobs as inactive
    - fetch_missing_descriptions: Fetch job descriptions
    - process_pending_applications: Process auto-apply queue
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    celery_app = get_celery_app()

    # Map task names to actual task paths
    task_map = {
        "scrape_all_companies": "tasks.scraper_tasks.scrape_all_companies",
        "scrape_by_category": "tasks.scraper_tasks.scrape_by_category",
        "cleanup_old_scraper_runs": "tasks.maintenance_tasks.cleanup_old_scraper_runs",
        "mark_stale_jobs_inactive": "tasks.maintenance_tasks.mark_stale_jobs_inactive",
        "fetch_missing_descriptions": "tasks.maintenance_tasks.fetch_missing_descriptions",
        "process_pending_applications": "tasks.auto_apply_tasks.process_pending_applications",
        "reset_daily_application_counts": "tasks.auto_apply_tasks.reset_daily_application_counts",
    }

    task_path = task_map.get(request.task_name)
    if not task_path:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task: {request.task_name}. Available: {list(task_map.keys())}"
        )

    try:
        task = celery_app.send_task(
            task_path,
            args=request.args or [],
            kwargs=request.kwargs or {},
        )

        return TriggerResponse(
            status="dispatched",
            task_id=task.id,
            message=f"Task {request.task_name} dispatched successfully",
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to dispatch task: {str(e)}")


@router.post("/tasks/trigger/{task_name}", response_model=TriggerResponse)
def trigger_named_task(
    task_name: str,
    category: Optional[str] = Query(None, description="Category for scrape_by_category"),
    current_user: User = Depends(get_current_user)
):
    """
    Trigger a specific task by name (simplified endpoint).
    """
    args = []
    if task_name == "scrape_by_category" and category:
        args = [category]

    return trigger_task(
        TriggerTaskRequest(task_name=task_name, args=args if args else None),
        current_user
    )


@router.get("/workers/ping")
def ping_workers(current_user: User = Depends(get_current_user)):
    """
    Ping all workers to check if they're alive.
    """
    celery_app = get_celery_app()

    try:
        inspect = celery_app.control.inspect(timeout=3.0)
        ping_result = inspect.ping()

        if not ping_result:
            return {
                "status": "no_workers",
                "message": "No Celery workers are currently connected",
                "workers": []
            }

        workers = []
        for hostname, response in ping_result.items():
            workers.append({
                "hostname": hostname,
                "status": "ok" if response.get("ok") == "pong" else "error",
            })

        return {
            "status": "ok",
            "message": f"{len(workers)} worker(s) responding",
            "workers": workers
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Could not ping workers: {str(e)}",
            "workers": []
        }


@router.post("/workers/purge/{queue_name}")
def purge_queue(
    queue_name: str,
    current_user: User = Depends(get_current_user)
):
    """
    Purge all pending tasks from a queue.
    """
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    valid_queues = ['default', 'scrapers_http', 'scrapers_browser', 'scrapers_orchestrator', 'maintenance']
    if queue_name not in valid_queues:
        raise HTTPException(status_code=400, detail=f"Invalid queue. Valid: {valid_queues}")

    celery_app = get_celery_app()

    try:
        # Purge the queue
        purged = celery_app.control.purge()

        return {
            "status": "success",
            "message": f"Purged tasks from queue",
            "purged_count": purged or 0
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to purge queue: {str(e)}")
