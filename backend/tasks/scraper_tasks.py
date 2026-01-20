"""
Celery Tasks for Running Scrapers.

Tasks:
- scrape_company_http: Run an HTTP scraper for a company
- scrape_company_browser: Run a Playwright scraper for a company
- scrape_all_companies: Orchestrate scraping all companies
- scrape_by_category: Scrape all companies in a category
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from celery import shared_task, group, chain
from sqlalchemy.orm import Session

from celery_app import celery_app
from database import SessionLocal
from models import ScraperRun, ScraperConfigDB, Company, Job
from scrapers.registry import ScraperRegistry, get_scraper
from scrapers.base import ScraperType, ScrapeResult
from scrapers.rate_limiter import get_rate_limiter

logger = logging.getLogger(__name__)


def get_db() -> Session:
    """Get a database session."""
    return SessionLocal()


def record_scraper_run(
    db: Session,
    company_slug: str,
    result: ScrapeResult,
    task_id: Optional[str] = None,
):
    """
    Record a scraper run in the database.

    Args:
        db: Database session
        company_slug: Company slug
        result: ScrapeResult from the scraper
        task_id: Celery task ID
    """
    run = ScraperRun(
        company_slug=company_slug,
        success=result.success,
        jobs_found=result.jobs_found,
        jobs_new=result.jobs_new,
        jobs_updated=result.jobs_updated,
        duration_seconds=result.duration_seconds,
        started_at=result.started_at,
        completed_at=result.completed_at,
        pages_scraped=result.pages_scraped,
        error_message=result.error_message,
        error_type=result.error_type.value if result.error_type else None,
        celery_task_id=task_id,
    )
    db.add(run)

    # Update scraper config health metrics
    config = db.query(ScraperConfigDB).filter(
        ScraperConfigDB.company_slug == company_slug
    ).first()

    if not config:
        config = ScraperConfigDB(company_slug=company_slug)
        db.add(config)

    config.total_runs = (config.total_runs or 0) + 1
    config.total_jobs_found = (config.total_jobs_found or 0) + result.jobs_found

    if result.success:
        config.last_success_at = datetime.utcnow()
        config.consecutive_failures = 0
    else:
        config.last_failure_at = datetime.utcnow()
        config.consecutive_failures = (config.consecutive_failures or 0) + 1

    db.commit()


def is_scraper_enabled(db: Session, company_slug: str) -> bool:
    """Check if a scraper is enabled."""
    config = db.query(ScraperConfigDB).filter(
        ScraperConfigDB.company_slug == company_slug
    ).first()

    if config:
        return config.is_enabled

    # Default to enabled if no config exists
    return True


@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def scrape_company_http(self, company_slug: str) -> dict:
    """
    Run an HTTP scraper for a company.

    Args:
        company_slug: Company slug to scrape

    Returns:
        Dict with scrape results
    """
    db = get_db()
    try:
        # Check if enabled
        if not is_scraper_enabled(db, company_slug):
            logger.info(f"Scraper {company_slug} is disabled, skipping")
            return {"status": "skipped", "reason": "disabled"}

        # Get the scraper
        rate_limiter = get_rate_limiter()
        scraper = get_scraper(company_slug, rate_limiter=rate_limiter)

        if not scraper:
            logger.error(f"No scraper found for {company_slug}")
            return {"status": "error", "reason": "scraper_not_found"}

        if scraper.config.scraper_type != ScraperType.HTTP:
            logger.warning(
                f"Scraper {company_slug} is not an HTTP scraper, "
                "use scrape_company_browser instead"
            )
            return {"status": "error", "reason": "wrong_scraper_type"}

        # Run the scraper
        logger.info(f"Starting HTTP scrape for {company_slug}")
        result = asyncio.run(scraper.run())

        # Save jobs if successful
        if result.success and result.jobs:
            from services.scraper_service import save_scraped_jobs
            jobs_new, jobs_updated = save_scraped_jobs(db, company_slug, result.jobs)
            result.jobs_new = jobs_new
            result.jobs_updated = jobs_updated

        # Record the run
        record_scraper_run(db, company_slug, result, task_id=self.request.id)

        return {
            "status": "success" if result.success else "failed",
            "company_slug": company_slug,
            "jobs_found": result.jobs_found,
            "jobs_new": result.jobs_new,
            "jobs_updated": result.jobs_updated,
            "duration_seconds": result.duration_seconds,
            "error": result.error_message,
        }

    except Exception as e:
        logger.exception(f"Error scraping {company_slug}")
        # Record the failure
        result = ScrapeResult(
            success=False,
            error_message=str(e),
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        record_scraper_run(db, company_slug, result, task_id=self.request.id)

        # Retry on transient errors
        raise self.retry(exc=e)

    finally:
        db.close()


@celery_app.task(bind=True, max_retries=3, default_retry_delay=120)
def scrape_company_browser(self, company_slug: str) -> dict:
    """
    Run a Playwright scraper for a company.

    Args:
        company_slug: Company slug to scrape

    Returns:
        Dict with scrape results
    """
    db = get_db()
    try:
        # Check if enabled
        if not is_scraper_enabled(db, company_slug):
            logger.info(f"Scraper {company_slug} is disabled, skipping")
            return {"status": "skipped", "reason": "disabled"}

        # Get the scraper
        rate_limiter = get_rate_limiter()

        # Import here to avoid circular imports
        from services.browser_pool import get_browser_pool

        async def run_with_browser():
            browser_pool = await get_browser_pool()
            scraper = get_scraper(
                company_slug,
                rate_limiter=rate_limiter,
                browser_pool=browser_pool,
            )

            if not scraper:
                return None, "scraper_not_found"

            if scraper.config.scraper_type != ScraperType.PLAYWRIGHT:
                return None, "wrong_scraper_type"

            return await scraper.run(), None

        result, error = asyncio.run(run_with_browser())

        if error:
            logger.error(f"Error for {company_slug}: {error}")
            return {"status": "error", "reason": error}

        # Save jobs if successful
        if result.success and result.jobs:
            from services.scraper_service import save_scraped_jobs
            jobs_new, jobs_updated = save_scraped_jobs(db, company_slug, result.jobs)
            result.jobs_new = jobs_new
            result.jobs_updated = jobs_updated

        # Record the run
        record_scraper_run(db, company_slug, result, task_id=self.request.id)

        return {
            "status": "success" if result.success else "failed",
            "company_slug": company_slug,
            "jobs_found": result.jobs_found,
            "jobs_new": result.jobs_new,
            "jobs_updated": result.jobs_updated,
            "duration_seconds": result.duration_seconds,
            "error": result.error_message,
        }

    except Exception as e:
        logger.exception(f"Error scraping {company_slug}")
        result = ScrapeResult(
            success=False,
            error_message=str(e),
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
        )
        record_scraper_run(db, company_slug, result, task_id=self.request.id)
        raise self.retry(exc=e)

    finally:
        db.close()


@celery_app.task
def scrape_all_companies() -> dict:
    """
    Orchestrate scraping all enabled companies.

    Dispatches tasks based on scraper type (HTTP vs Playwright).

    Returns:
        Dict with task counts
    """
    logger.info("Starting scrape_all_companies orchestration")

    # Load all scrapers
    all_scrapers = ScraperRegistry.get_all()

    db = get_db()
    try:
        http_tasks = []
        browser_tasks = []

        for slug, scraper_cls in all_scrapers.items():
            # Check if enabled
            if not is_scraper_enabled(db, slug):
                logger.info(f"Skipping disabled scraper: {slug}")
                continue

            if scraper_cls.config.scraper_type == ScraperType.HTTP:
                http_tasks.append(scrape_company_http.s(slug))
            else:
                browser_tasks.append(scrape_company_browser.s(slug))

        # Dispatch tasks
        # HTTP tasks can run more in parallel
        if http_tasks:
            group(http_tasks).apply_async(queue="scrapers_http")
            logger.info(f"Dispatched {len(http_tasks)} HTTP scraper tasks")

        # Browser tasks should be more limited
        if browser_tasks:
            group(browser_tasks).apply_async(queue="scrapers_browser")
            logger.info(f"Dispatched {len(browser_tasks)} browser scraper tasks")

        return {
            "status": "dispatched",
            "http_tasks": len(http_tasks),
            "browser_tasks": len(browser_tasks),
            "total": len(http_tasks) + len(browser_tasks),
        }

    finally:
        db.close()


@celery_app.task
def scrape_by_category(category: str) -> dict:
    """
    Scrape all companies in a category.

    Args:
        category: Category name (big_tech, enterprise, finance, other)

    Returns:
        Dict with task counts
    """
    logger.info(f"Starting scrape for category: {category}")

    scrapers = ScraperRegistry.get_by_category(category)

    db = get_db()
    try:
        http_tasks = []
        browser_tasks = []

        for slug, scraper_cls in scrapers.items():
            if not is_scraper_enabled(db, slug):
                continue

            if scraper_cls.config.scraper_type == ScraperType.HTTP:
                http_tasks.append(scrape_company_http.s(slug))
            else:
                browser_tasks.append(scrape_company_browser.s(slug))

        if http_tasks:
            group(http_tasks).apply_async(queue="scrapers_http")

        if browser_tasks:
            group(browser_tasks).apply_async(queue="scrapers_browser")

        return {
            "status": "dispatched",
            "category": category,
            "http_tasks": len(http_tasks),
            "browser_tasks": len(browser_tasks),
            "total": len(http_tasks) + len(browser_tasks),
        }

    finally:
        db.close()


@celery_app.task
def scrape_single_company(company_slug: str) -> dict:
    """
    Scrape a single company (auto-detects scraper type).

    Args:
        company_slug: Company slug

    Returns:
        Task result
    """
    scraper_cls = ScraperRegistry.get(company_slug)

    if not scraper_cls:
        return {"status": "error", "reason": "scraper_not_found"}

    if scraper_cls.config.scraper_type == ScraperType.HTTP:
        return scrape_company_http.delay(company_slug).get()
    else:
        return scrape_company_browser.delay(company_slug).get()
