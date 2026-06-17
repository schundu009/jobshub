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
        "tasks.auto_apply_tasks",
        "tasks.apify_tasks",
    ],
)

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
        "tasks.auto_apply_tasks.submit_application": {"queue": "scrapers_browser"},
        "tasks.auto_apply_tasks.process_pending_applications": {"queue": "maintenance"},
        "tasks.auto_apply_tasks.reset_daily_application_counts": {"queue": "maintenance"},
        "tasks.apify_tasks.scrape_apify_indeed": {"queue": "scrapers_http"},
        "tasks.apify_tasks.scrape_apify_linkedin": {"queue": "scrapers_http"},
        "tasks.apify_tasks.scrape_all_apify": {"queue": "scrapers_orchestrator"},
    },

    # Define queues
    task_queues=(
        Queue("default", routing_key="default"),
        Queue("scrapers_http", routing_key="scrapers.http"),
        Queue("scrapers_browser", routing_key="scrapers.browser"),
        Queue("scrapers_orchestrator", routing_key="scrapers.orchestrator"),
        Queue("maintenance", routing_key="maintenance"),
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
        "tasks.scraper_tasks.scrape_all_companies": {
            "soft_time_limit": 300,  # Orchestrator: 5 min soft
            "time_limit": 360,  # 6 min hard
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

    # Retry settings
    task_acks_late=True,  # Acknowledge after task completes
    task_reject_on_worker_lost=True,  # Re-queue if worker dies

    # Beat schedule for periodic tasks
    beat_schedule={
        # Run all scrapers every 6 hours
        "scrape-all-companies": {
            "task": "tasks.scraper_tasks.scrape_all_companies",
            "schedule": crontab(minute=0, hour=f"*/{settings.scraper_schedule_hours}"),
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
        # Process pending auto-apply applications every 15 minutes
        "process-pending-applications": {
            "task": "tasks.auto_apply_tasks.process_pending_applications",
            "schedule": crontab(minute="*/15"),
            "options": {"queue": "maintenance"},
        },
        # Reset daily application counts at midnight
        "reset-daily-application-counts": {
            "task": "tasks.auto_apply_tasks.reset_daily_application_counts",
            "schedule": crontab(minute=0, hour=0),
            "options": {"queue": "maintenance"},
        },
        # Check scraper health after each scrape cycle (every 6h + 30min delay for scrapers to finish)
        "check-scraper-health": {
            "task": "tasks.maintenance_tasks.check_scraper_health_and_notify",
            "schedule": crontab(minute=30, hour="0,6,12,18"),
            "options": {"queue": "maintenance"},
        },
        # Fetch missing job descriptions every 30 minutes
        "fetch-missing-descriptions": {
            "task": "tasks.maintenance_tasks.fetch_missing_descriptions",
            "schedule": crontab(minute="*/30"),
            "options": {"queue": "maintenance"},
        },
        # Apify scrapers — once daily to stay within $5/month free tier
        "apify-scrape-all": {
            "task": "tasks.apify_tasks.scrape_all_apify",
            "schedule": crontab(minute=30, hour=3),
            "options": {"queue": "scrapers_orchestrator"},
        },
    },
)


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
