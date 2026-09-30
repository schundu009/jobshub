"""
Celery Management API Routes.

Endpoints for:
- Viewing worker and queue status
- Triggering tasks manually
- Managing schedules
- Viewing task history
"""

from typing import Optional, List
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database import get_db
from models import User, ScraperRun
from middleware.auth import get_current_admin_detached
from config import settings
from services.redis_service import redis_service
from services import app_settings

logger = logging.getLogger(__name__)

# Admin-only. The detached variant releases the request's DB connection right
# after the auth lookup, so slow worker broadcasts don't pin a pooled connection.
router = APIRouter(
    prefix="/api/celery",
    tags=["celery"],
    dependencies=[Depends(get_current_admin_detached)],
)


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
    auto_apply_enabled: bool = False
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


def declared_queue_names() -> List[str]:
    """Queue names declared in celery_app.conf.task_queues."""
    return [q.name for q in (get_celery_app().conf.task_queues or [])]


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
        queue_names = declared_queue_names()
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
def get_celery_status(current_user: User = Depends(get_current_admin_detached)):
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


class SchedulesResponse(BaseModel):
    schedules: List[ScheduleItem]
    settings: dict


def _format_schedule(schedule) -> str:
    if hasattr(schedule, 'minute') and hasattr(schedule, 'hour'):
        minute = getattr(schedule, '_orig_minute', schedule.minute)
        hour = getattr(schedule, '_orig_hour', schedule.hour)
        return f"cron({minute} {hour} * * *)"
    return str(schedule)


@router.get("/schedules", response_model=SchedulesResponse)
def get_schedules(
    current_user: User = Depends(get_current_admin_detached),
    db: Session = Depends(get_db)
):
    """
    Get configured task schedules plus the admin-editable settings
    ({scraper_interval_hours, auto_apply_enabled, description_fetch_enabled}).
    Cached in Redis for 20s.
    """
    cached = redis_service.cache_get(CELERY_SCHEDULES_CACHE_KEY)
    if cached is not None and isinstance(cached, dict):
        return cached

    celery_app = get_celery_app()
    current = app_settings.schedule_settings(db)
    last_run = app_settings.get_datetime(db, app_settings.SCRAPER_LAST_RUN_KEY)

    schedules = []
    for name, config in celery_app.conf.beat_schedule.items():
        task = config.get('task', '')
        # Determine if enabled based on settings (the tasks check these flags too)
        enabled = True
        if 'auto_apply' in task or 'application' in name.lower():
            enabled = current["auto_apply_enabled"]
        elif 'description' in name.lower():
            enabled = current["description_fetch_enabled"]

        item = ScheduleItem(
            name=name,
            task=task,
            schedule=_format_schedule(config.get('schedule')),
            enabled=enabled,
            last_run=None,
            next_run=None,
        )
        if task == "tasks.scraper_tasks.scrape_all_companies":
            item.schedule = f"every {current['scraper_interval_hours']}h (checked {item.schedule})"
            item.last_run = last_run.isoformat() if last_run else None
        schedules.append(item)

    payload = {
        "schedules": [item.model_dump() for item in schedules],
        "settings": current,
    }
    redis_service.cache_set(CELERY_SCHEDULES_CACHE_KEY, payload, CELERY_CACHE_TTL)
    return payload


@router.put("/schedules")
def update_schedules(
    update: ScheduleUpdate,
    current_user: User = Depends(get_current_admin_detached),
    db: Session = Depends(get_db)
):
    """
    Update schedule settings. Takes effect without a Beat restart:
    scrape_all_companies skips runs until scraper_interval_hours have passed
    since the last orchestrated run, and fetch_missing_descriptions /
    process_pending_applications return early when disabled.
    """
    app_settings.set_setting(db, app_settings.SCRAPER_INTERVAL_KEY, str(update.scraper_interval_hours))
    app_settings.set_setting(db, app_settings.AUTO_APPLY_ENABLED_KEY, str(update.auto_apply_enabled).lower())
    app_settings.set_setting(
        db, app_settings.DESCRIPTION_FETCH_ENABLED_KEY, str(update.description_fetch_enabled).lower()
    )
    db.commit()
    redis_service.cache_delete(CELERY_SCHEDULES_CACHE_KEY)

    return {
        "status": "success",
        "message": "Schedules updated. Changes apply from the next scheduled check.",
        "settings": {
            "scraper_interval_hours": update.scraper_interval_hours,
            "auto_apply_enabled": update.auto_apply_enabled,
            "description_fetch_enabled": update.description_fetch_enabled,
        }
    }


RESULT_KEY_PREFIX = "celery-task-meta-"
RESULT_SCAN_MAX_KEYS = 200  # bound the SCAN so this stays fast


def _recent_celery_results(max_keys: int = RESULT_SCAN_MAX_KEYS) -> List[TaskInfo]:
    """
    Recent task results from the Redis result backend (results expire after
    result_expires=1h). Only read when the result backend is the same Redis
    as redis_service; bounded to ``max_keys`` keys. Task name/args are only
    present when result_extended is on, so they may be missing.
    """
    backend = settings.celery_result_backend or ""
    if not backend.startswith("redis") or backend != settings.redis_url:
        return []
    client = get_redis_client()
    if client is None or not redis_service.ping():
        return []
    try:
        keys = []
        for key in client.scan_iter(match=f"{RESULT_KEY_PREFIX}*", count=100):
            keys.append(key)
            if len(keys) >= max_keys:
                break
        if not keys:
            return []
        values = client.mget(keys)
    except Exception as e:
        logger.debug(f"celery result scan failed: {e}")
        return []

    tasks = []
    for key, raw in zip(keys, values):
        if not raw:
            continue
        try:
            meta = json.loads(raw)
        except (TypeError, ValueError):
            continue
        status = meta.get("status") or "UNKNOWN"
        result = meta.get("result")
        tasks.append(TaskInfo(
            task_id=meta.get("task_id") or str(key)[len(RESULT_KEY_PREFIX):],
            name=meta.get("name") or "celery task",
            status=status,
            args=json.dumps(meta.get("args"))[:200] if meta.get("args") else None,
            started_at=None,
            completed_at=meta.get("date_done"),
            result=json.dumps(result)[:500] if status == "SUCCESS" and result is not None else None,
            error=str(result)[:500] if status == "FAILURE" else None,
        ))
    return tasks


@router.get("/tasks/recent", response_model=List[TaskInfo])
def get_recent_tasks(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: User = Depends(get_current_admin_detached),
    db: Session = Depends(get_db)
):
    """
    Recent task executions: scraper runs from the DB, plus any results still in
    the Redis result backend (expire after 1h; scan bounded to 200 keys).
    Sorted newest first.
    """
    runs = db.query(ScraperRun).order_by(
        ScraperRun.run_at.desc()
    ).limit(limit).all()

    tasks = []
    seen_ids = set()
    for run in runs:
        if run.celery_task_id:
            seen_ids.add(run.celery_task_id)
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

    tasks.extend(t for t in _recent_celery_results() if t.task_id not in seen_ids)
    tasks.sort(key=lambda t: t.completed_at or t.started_at or "", reverse=True)
    return tasks[:limit]


@router.post("/tasks/trigger", response_model=TriggerResponse)
def trigger_task(
    request: TriggerTaskRequest,
    current_user: User = Depends(get_current_admin_detached)
):
    """
    Manually trigger a Celery task.

    Available tasks:
    - scrape_all_companies: Run all scrapers
    - scrape_by_category: Run scrapers for a category (args: ["big_tech"])
    - cleanup_old_scraper_runs: Clean up old run records
    - mark_stale_jobs_inactive: Mark old jobs as inactive
    - fetch_missing_descriptions: Fetch job descriptions
    - apply_nightly_matching: Rebuild Auto Apply match queues for enabled users
    - apply_prepare_auto: Prepare auto-mode applications (respects daily caps)
    """
    celery_app = get_celery_app()

    # Map task names to actual task paths
    task_map = {
        "scrape_all_companies": "tasks.scraper_tasks.scrape_all_companies",
        "scrape_by_category": "tasks.scraper_tasks.scrape_by_category",
        "cleanup_old_scraper_runs": "tasks.maintenance_tasks.cleanup_old_scraper_runs",
        "mark_stale_jobs_inactive": "tasks.maintenance_tasks.mark_stale_jobs_inactive",
        "fetch_missing_descriptions": "tasks.maintenance_tasks.fetch_missing_descriptions",
        "apply_nightly_matching": "tasks.apply_tasks.nightly_matching",
        "apply_prepare_auto": "tasks.apply_tasks.prepare_auto_applications",
    }

    task_path = task_map.get(request.task_name)
    if not task_path:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown task: {request.task_name}. Available: {list(task_map.keys())}"
        )

    kwargs = dict(request.kwargs or {})
    if request.task_name == "scrape_all_companies":
        # A manual trigger bypasses the scrape-interval gate.
        kwargs.setdefault("force", True)

    try:
        task = celery_app.send_task(
            task_path,
            args=request.args or [],
            kwargs=kwargs,
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
    current_user: User = Depends(get_current_admin_detached)
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

