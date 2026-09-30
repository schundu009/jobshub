"""
Celery Application Configuration.

Sets up Celery with Redis as the broker and result backend.
Includes task routing, rate limiting, and scheduled tasks.

Usage:
    # Start worker
    celery -A celery_app worker --loglevel=info

    # Start beat scheduler
    celery -A celery_app beat --loglevel=info

    # Monitor with Flower
    celery -A celery_app flower
"""

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_process_init
from kombu import Queue

from config import settings


# Create Celery app
celery_app = Celery(
    "jobportal",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "tasks.scraper_tasks",
        "tasks.maintenance_tasks",
        "tasks.apply_tasks",
        "tasks.apify_tasks",
        "contracts.tasks",
    ],
)

# Scrape cadence. Beat checks every hour; scrape_all_companies itself skips
# unless AppSetting scraper_interval_hours (admin Settings > Schedules,
# default settings.scraper_schedule_hours) has passed since its last run.
SCRAPE_INTERVAL_HOURS = max(1, min(24, int(settings.scraper_schedule_hours or 6)))

BEAT_SCHEDULE = {
    "scrape-all-companies": {
        "task": "tasks.scraper_tasks.scrape_all_companies",
        "schedule": crontab(minute=0),
        "options": {"queue": "scrapers_orchestrator"},
    },
    # Clean up old scraper runs daily at 3 AM
    "cleanup-old-runs": {
        "task": "tasks.maintenance_tasks.cleanup_old_scraper_runs",
        "schedule": crontab(minute=0, hour=3),
        "options": {"queue": "maintenance"},
    },
    # Mark stale jobs as inactive daily at 4 AM
    "mark-stale-jobs": {
        "task": "tasks.maintenance_tasks.mark_stale_jobs_inactive",
        "schedule": crontab(minute=0, hour=4),
        "options": {"queue": "maintenance"},
    },
    # Health check 30 min after each default scrape cycle.
    "check-scraper-health": {
        "task": "tasks.maintenance_tasks.check_scraper_health_and_notify",
        "schedule": crontab(minute=30, hour=f"*/{SCRAPE_INTERVAL_HOURS}"),
        "options": {"queue": "maintenance"},
    },
    # Fetch missing job descriptions every 30 minutes (skips when disabled in Schedules)
    "fetch-missing-descriptions": {
        "task": "tasks.maintenance_tasks.fetch_missing_descriptions",
        "schedule": crontab(minute="*/30"),
        "options": {"queue": "maintenance"},
    },
    # IT/tech jobs only: retire non-IT rows (new ones are already skipped on save)
    "deactivate-non-it-jobs": {
        "task": "tasks.maintenance_tasks.deactivate_non_it_jobs",
        "schedule": crontab(minute=15, hour=4),
        "options": {"queue": "maintenance"},
    },
    # Auto-heal broken ATS scrapers daily after health check runs
    "auto-heal-scrapers": {
        "task": "tasks.maintenance_tasks.auto_heal_scrapers",
        "schedule": crontab(minute=45, hour=1),
        "options": {"queue": "maintenance"},
    },
    # Apify scrapers — once daily to stay within $5/month free tier
    "apify-scrape-all": {
        "task": "tasks.apify_tasks.scrape_all_apify",
        "schedule": crontab(minute=30, hour=3),
        "options": {"queue": "scrapers_orchestrator"},
    },
    # Cariara Auto Apply (routes/apply.py). Nothing here submits applications:
    # matching rebuilds each enabled user's queue; preparation drafts
    # auto-mode applications up to the user's daily cap.
    "apply-nightly-matching": {
        "task": "tasks.apply_tasks.nightly_matching",
        "schedule": crontab(minute=0, hour=13),
        "options": {"queue": "default"},
    },
    # Contract roles (contracts package, queue "contracts"): scrape staffing
    # boards every 6h at :15 past (offset from the full-time :00 cycle) and
    # expire roles past contract_max_age_days daily.
    "contracts-scrape-all": {
        "task": "contracts.tasks.scrape_all_contracts",
        "schedule": crontab(minute=15, hour="*/6"),
        "options": {"queue": "contracts"},
    },
    "contracts-expire": {
        "task": "contracts.tasks.expire_contract_jobs",
        "schedule": crontab(minute=10, hour=4),
        "options": {"queue": "contracts"},
    },
    "apply-prepare-auto": {
        "task": "tasks.apply_tasks.prepare_auto_applications",
        "schedule": crontab(minute=20),
        "options": {"queue": "default"},
    },
}

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,

    # Result settings
    result_expires=3600,  # Results expire after 1 hour
    task_track_started=True,

    # Worker settings
    worker_prefetch_multiplier=1,  # Don't prefetch, process one at a time
    worker_concurrency=2,  # Reduced from 4 to prevent OOM on Railway
    worker_max_tasks_per_child=25,  # Restart child more often to prevent memory leaks
    worker_max_memory_per_child=512_000,  # Restart child if >512MB (prevents OOM)
    worker_lost_wait=30,  # Wait 30s before declaring worker lost

    # Task routing - separate queues for different task types
    task_routes={
        "tasks.scraper_tasks.scrape_company_http": {"queue": "scrapers_http"},
        "tasks.scraper_tasks.scrape_company_browser": {"queue": "scrapers_browser"},
        "tasks.scraper_tasks.scrape_all_companies": {"queue": "scrapers_orchestrator"},
        "tasks.maintenance_tasks.*": {"queue": "maintenance"},
        "tasks.apply_tasks.*": {"queue": "default"},
        "tasks.apify_tasks.scrape_apify_indeed": {"queue": "scrapers_http"},
        "tasks.apify_tasks.scrape_apify_linkedin": {"queue": "scrapers_http"},
        "tasks.apify_tasks.scrape_all_apify": {"queue": "scrapers_orchestrator"},
        "contracts.tasks.*": {"queue": "contracts"},
    },

    # Define queues
    task_queues=(
        Queue("default", routing_key="default"),
        Queue("scrapers_http", routing_key="scrapers.http"),
        Queue("scrapers_browser", routing_key="scrapers.browser"),
        Queue("scrapers_orchestrator", routing_key="scrapers.orchestrator"),
        Queue("maintenance", routing_key="maintenance"),
        Queue("contracts", routing_key="contracts"),
    ),

    # Default queue
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",

    # Task timeouts (hard kill if task exceeds these)
    task_soft_time_limit=120,  # Soft limit: 2 min (raises SoftTimeLimitExceeded)
    task_time_limit=180,  # Hard limit: 3 min (kills the task)

    # Rate limits and per-task overrides
    task_annotations={
        "contracts.tasks.scrape_contract_source": {
            "rate_limit": "10/m",
            "soft_time_limit": 300,
            "time_limit": 360,
        },
        "contracts.tasks.expire_contract_jobs": {
            "soft_time_limit": 600,
            "time_limit": 660,
            "reject_on_worker_lost": False,
        },
        "tasks.scraper_tasks.scrape_company_http": {
            "rate_limit": "10/m",
            "soft_time_limit": 120,  # HTTP scrapers: 2 min soft
            "time_limit": 180,  # 3 min hard
        },
        "tasks.scraper_tasks.scrape_company_browser": {
            "rate_limit": "5/m",
            "soft_time_limit": 300,  # Browser scrapers: 5 min soft
            "time_limit": 360,  # 6 min hard
        },
        # Long-running maintenance/orchestration tasks. The 120/180s defaults
        # killed them mid-run, and with acks_late + reject_on_worker_lost a
        # killed task was redelivered forever - so these get 25/30 min and are
        # NOT re-queued when the worker dies.
        "tasks.scraper_tasks.scrape_all_companies": {
            "soft_time_limit": 1500,
            "time_limit": 1800,
            "reject_on_worker_lost": False,
        },
        "tasks.maintenance_tasks.fetch_missing_descriptions": {
            "soft_time_limit": 1500,
            "time_limit": 1800,
            "reject_on_worker_lost": False,
        },
        "tasks.maintenance_tasks.auto_heal_scrapers": {
            "soft_time_limit": 1500,
            "time_limit": 1800,
            "reject_on_worker_lost": False,
        },
        # Auto Apply orchestration loops over users; drafting calls ATS + AI.
        "tasks.apply_tasks.nightly_matching": {
            "soft_time_limit": 1500,
            "time_limit": 1800,
            "reject_on_worker_lost": False,
        },
        "tasks.apply_tasks.prepare_auto_applications": {
            "soft_time_limit": 1500,
            "time_limit": 1800,
            "reject_on_worker_lost": False,
        },
        "tasks.apply_tasks.prepare_for_user": {
            "soft_time_limit": 600,
            "time_limit": 660,
            "reject_on_worker_lost": False,
        },
        # Apify actors can take 10+ minutes — give them ample time
        "tasks.apify_tasks.scrape_apify_indeed": {
            "soft_time_limit": 3300,  # 55 min soft (200+ queries × up to 300s each)
            "time_limit": 3600,  # 60 min hard
        },
        "tasks.apify_tasks.scrape_apify_linkedin": {
            "soft_time_limit": 720,  # 12 min soft
            "time_limit": 780,  # 13 min hard
        },
        "tasks.apify_tasks.scrape_all_apify": {
            "soft_time_limit": 1800,  # 30 min soft (orchestrator runs all actors)
            "time_limit": 1860,  # 31 min hard
        },
    },

    # Redis re-delivers a message that stays unacked longer than the visibility
    # timeout (default 1h). With ~250 scrapers fanned out at 10/m (and
    # countdown-staggered), tasks can wait well over an hour, so they were being
    # delivered twice. 4h covers a full cycle.
    broker_transport_options={"visibility_timeout": 4 * 60 * 60},
    result_backend_transport_options={"visibility_timeout": 4 * 60 * 60},

    # Retry settings
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,  # Re-queue if worker dies

    # Beat schedule for periodic tasks
    beat_schedule=BEAT_SCHEDULE,
)


@worker_process_init.connect
def _reset_db_pool_after_fork(**_):
    """
    database.py connects at import (startup migrations), so the prefork parent
    holds pooled Postgres sockets that every child inherits. Two children
    talking over one socket corrupts the protocol ("lost synchronization with
    server", then PendingRollbackError on every retry). Drop the inherited
    pool in each child without closing the parent's sockets.
    """
    from database import engine
    if engine is not None:
        engine.dispose(close=False)


# Optional: Configure Sentry for error tracking
if settings.sentry_dsn:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.1,
    )


if __name__ == "__main__":
    celery_app.start()
