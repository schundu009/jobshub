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
from datetime import datetime, timedelta
from typing import Optional

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.orm import Session

from celery_app import celery_app
from database import SessionLocal
from models import ScraperRun, ScraperConfigDB, Company, Job
from scrapers.registry import ScraperRegistry, get_scraper
from scrapers.base import ScraperType, ScrapeResult, ScraperErrorType
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
    _flag_suspicious_empty_result(db, company_slug, result)

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
        error_type=getattr(result.error_type, "value", result.error_type) or None,
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


def _flag_suspicious_empty_result(db: Session, company_slug: str, result: ScrapeResult) -> None:
    """
    A "successful" 0-job scrape of a board whose last successful run found jobs
    is almost always a silent breakage (board moved ATS, API shape changed, all
    postings filtered). Record it as a failure with error_type=empty_result so
    it shows up in scraper health. This only bumps consecutive_failures; it never
    disables the scraper by itself. Scrapers configured with allow_empty=True
    (boards that legitimately go to zero) are exempt.
    """
    if not result.success or (result.jobs_found or 0) > 0 or result.jobs:
        return
    scraper_cls = ScraperRegistry.get(company_slug)
    if scraper_cls is not None and getattr(scraper_cls.config, "allow_empty", False):
        return
    last_success = db.query(ScraperRun.jobs_found).filter(
        ScraperRun.company_slug == company_slug,
        ScraperRun.success == True,  # noqa: E712
    ).order_by(ScraperRun.run_at.desc(), ScraperRun.id.desc()).first()
    if not last_success or not (last_success[0] or 0) > 0:
        return
    result.success = False
    result.error_type = ScraperErrorType.EMPTY_RESULT
    result.error_message = result.error_message or (
        f"0 jobs returned; the last successful run found {last_success[0]}. "
        "Board moved, API changed, or all postings filtered out."
    )
    logger.warning(f"{company_slug}: empty result after {last_success[0]} jobs - recorded as failure")


def _record_failure(company_slug: str, message: str, error_type, task_id: Optional[str]) -> None:
    """Record a failed run on a fresh session; never raises (the worker must survive)."""
    fail_db = get_db()
    try:
        now = datetime.utcnow()
        record_scraper_run(
            fail_db,
            company_slug,
            ScrapeResult(
                success=False,
                error_message=message[:1000],
                error_type=error_type,
                started_at=now,
                completed_at=now,
            ),
            task_id=task_id,
        )
    except Exception:
        logger.exception(f"Failed to record {error_type} failure for {company_slug}")
        try:
            fail_db.rollback()
        except Exception:
            pass
    finally:
        fail_db.close()


def is_scraper_enabled(db: Session, company_slug: str) -> bool:
    """Check if a scraper is enabled."""
    try:
        config = db.query(ScraperConfigDB).filter(
            ScraperConfigDB.company_slug == company_slug
        ).first()

        if config:
            return config.is_enabled
    except Exception as e:
        # Session may be corrupted, try with fresh session
        logger.warning(f"Session error checking scraper {company_slug}, retrying: {e}")
        fresh_db = SessionLocal()
        try:
            config = fresh_db.query(ScraperConfigDB).filter(
                ScraperConfigDB.company_slug == company_slug
            ).first()
            if config:
                return config.is_enabled
        finally:
            fresh_db.close()

    # Default to enabled if no config exists
    return True


@celery_app.task(bind=True, max_retries=2, default_retry_delay=60)
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

        # Save jobs if successful - use fresh DB connection to avoid stale sessions
        if result.success and result.jobs:
            save_db = get_db()
            try:
                from services.scraper_service import save_scraped_jobs
                jobs_new, jobs_updated = save_scraped_jobs(save_db, company_slug, result.jobs)
                result.jobs_new = jobs_new
                result.jobs_updated = jobs_updated
            except Exception as save_err:
                logger.error(f"Error saving jobs for {company_slug}: {save_err}")
            finally:
                save_db.close()

        # Record the run with a fresh connection
        record_db = get_db()
        try:
            record_scraper_run(record_db, company_slug, result, task_id=self.request.id)
        except Exception as rec_err:
            logger.error(f"Error recording run for {company_slug}: {rec_err}")
        finally:
            record_db.close()

        return {
            "status": "success" if result.success else "failed",
            "company_slug": company_slug,
            "jobs_found": result.jobs_found,
            "jobs_new": result.jobs_new,
            "jobs_updated": result.jobs_updated,
            "duration_seconds": result.duration_seconds,
            "error": result.error_message,
        }

    except SoftTimeLimitExceeded:
        # Record it: a timeout used to leave no ScraperRun row at all, so big
        # scrapers that always time out showed as "never run".
        logger.warning(f"Scraper {company_slug} timed out (soft limit)")
        _record_failure(company_slug, "soft time limit exceeded", ScraperErrorType.TIMEOUT, self.request.id)
        return {"status": "timeout", "company_slug": company_slug, "error": "soft time limit exceeded"}

    except Exception as e:
        logger.exception(f"Error scraping {company_slug}")
        # Record the failure - never let this crash the worker
        _record_failure(company_slug, str(e), "exception", self.request.id)

        # Only retry on transient errors, not on persistent DB issues
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {"status": "error", "company_slug": company_slug, "error": str(e)}

    finally:
        try:
            db.close()
        except Exception:
            pass


@celery_app.task(bind=True, max_retries=2, default_retry_delay=120)
def scrape_company_browser(self, company_slug: str) -> dict:
    """
    Run a Playwright scraper for a company.

    Args:
        company_slug: Company slug to scrape

    Returns:
        Dict with scrape results
    """
    # Check if enabled with a short-lived connection
    db = get_db()
    try:
        if not is_scraper_enabled(db, company_slug):
            logger.info(f"Scraper {company_slug} is disabled, skipping")
            return {"status": "skipped", "reason": "disabled"}
    except Exception as e:
        logger.warning(f"Error checking if {company_slug} is enabled: {e}")
    finally:
        try:
            db.close()
        except Exception:
            pass

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

    try:
        try:
            result, error = asyncio.run(run_with_browser())
        except Exception as browser_err:
            err_msg = str(browser_err)
            if "Connection closed" in err_msg or "Browser" in err_msg:
                logger.error(f"Browser launch failed for {company_slug}: {err_msg}")
                # Record failure but don't retry browser errors — they're likely OOM
                fail_db = get_db()
                try:
                    fail_result = ScrapeResult(
                        success=False,
                        error_message=f"Browser crash: {err_msg[:200]}",
                        started_at=datetime.utcnow(),
                        completed_at=datetime.utcnow(),
                    )
                    record_scraper_run(fail_db, company_slug, fail_result, task_id=self.request.id)
                except Exception:
                    pass
                finally:
                    fail_db.close()
                return {"status": "failed", "company_slug": company_slug, "error": f"Browser crash: {err_msg[:200]}"}
            raise

        if error:
            logger.error(f"Error for {company_slug}: {error}")
            return {"status": "error", "reason": error}

        # Save jobs with a FRESH database connection
        if result.success and result.jobs:
            save_db = get_db()
            try:
                from services.scraper_service import save_scraped_jobs
                jobs_new, jobs_updated = save_scraped_jobs(save_db, company_slug, result.jobs)
                result.jobs_new = jobs_new
                result.jobs_updated = jobs_updated
            except Exception as save_err:
                logger.error(f"Error saving jobs for {company_slug}: {save_err}")
            finally:
                save_db.close()

        # Record the run with a fresh connection
        record_db = get_db()
        try:
            record_scraper_run(record_db, company_slug, result, task_id=self.request.id)
        except Exception as rec_err:
            logger.error(f"Error recording run for {company_slug}: {rec_err}")
        finally:
            record_db.close()

        return {
            "status": "success" if result.success else "failed",
            "company_slug": company_slug,
            "jobs_found": result.jobs_found,
            "jobs_new": result.jobs_new,
            "jobs_updated": result.jobs_updated,
            "duration_seconds": result.duration_seconds,
            "error": result.error_message,
        }

    except SoftTimeLimitExceeded:
        logger.warning(f"Browser scraper {company_slug} timed out (soft limit)")
        _record_failure(company_slug, "soft time limit exceeded", ScraperErrorType.TIMEOUT, self.request.id)
        return {"status": "timeout", "company_slug": company_slug, "error": "soft time limit exceeded"}

    except Exception as e:
        logger.exception(f"Error scraping {company_slug}")
        # Record failure - never let this crash the worker
        _record_failure(company_slug, str(e), "exception", self.request.id)

        if self.request.retries < self.max_retries:
            raise self.retry(exc=e)
        return {"status": "error", "company_slug": company_slug, "error": str(e)}


DISPATCH_STAGGER_SECONDS = 2


def _dispatch_staggered(signatures: list, queue: str) -> None:
    for i, sig in enumerate(signatures):
        sig.apply_async(queue=queue, countdown=i * DISPATCH_STAGGER_SECONDS)


# Beat fires scrape_all_companies hourly; runs closer together than the
# admin-configured interval are skipped. Slack absorbs beat jitter so a 6h
# interval doesn't slip to 7h.
INTERVAL_SLACK = timedelta(minutes=10)


def _interval_gate(force: bool) -> Optional[dict]:
    """
    Returns a "skipped" result if the last orchestrated run is more recent than
    AppSetting scraper_interval_hours; otherwise records now as the last run and
    returns None. Errors reading the setting never block a scrape.
    """
    from services import app_settings

    db = get_db()
    try:
        now = datetime.utcnow()
        interval_hours = app_settings.schedule_settings(db)["scraper_interval_hours"]
        last_run = app_settings.get_datetime(db, app_settings.SCRAPER_LAST_RUN_KEY)
        if not force and last_run and now - last_run < timedelta(hours=interval_hours) - INTERVAL_SLACK:
            logger.info(
                f"scrape_all_companies skipped: last run {last_run.isoformat()}, "
                f"interval {interval_hours}h"
            )
            return {
                "status": "skipped",
                "skipped": "interval",
                "last_run": last_run.isoformat(),
                "interval_hours": interval_hours,
            }
        app_settings.set_setting(
            db, app_settings.SCRAPER_LAST_RUN_KEY, now.isoformat(),
            description="Last time scrape_all_companies dispatched scrapers",
        )
        db.commit()
        return None
    except Exception as e:
        logger.warning(f"scrape interval check failed, running anyway: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        return None
    finally:
        db.close()


@celery_app.task
def scrape_all_companies(force: bool = False) -> dict:
    """
    Orchestrate scraping all enabled companies.

    Dispatches tasks based on scraper type (HTTP vs Playwright). Unless
    ``force`` is set (manual/webhook triggers), skips when the last
    orchestrated run is newer than AppSetting scraper_interval_hours.

    Returns:
        Dict with task counts
    """
    logger.info("Starting scrape_all_companies orchestration")

    skipped = _interval_gate(force)
    if skipped:
        return skipped

    try:
        # Load all scrapers
        all_scrapers = ScraperRegistry.get_all()

        db = get_db()
        try:
            # Expire all cached objects to prevent stale state
            db.expire_all()

            http_tasks = []
            browser_tasks = []

            for slug, scraper_cls in all_scrapers.items():
                # Check if enabled - don't let one bad check stop the whole run
                try:
                    if not is_scraper_enabled(db, slug):
                        logger.info(f"Skipping disabled scraper: {slug}")
                        continue
                except Exception as e:
                    logger.warning(f"Error checking scraper {slug}, including it anyway: {e}")

                if scraper_cls.config.scraper_type == ScraperType.HTTP:
                    http_tasks.append(scrape_company_http.s(slug))
                else:
                    browser_tasks.append(scrape_company_browser.s(slug))

            # Dispatch, staggered DISPATCH_STAGGER_SECONDS apart so ~250 tasks
            # don't all sit unacked on the broker at once.
            _dispatch_staggered(http_tasks, "scrapers_http")
            logger.info(f"Dispatched {len(http_tasks)} HTTP scraper tasks")
            _dispatch_staggered(browser_tasks, "scrapers_browser")
            logger.info(f"Dispatched {len(browser_tasks)} browser scraper tasks")

            return {
                "status": "dispatched",
                "http_tasks": len(http_tasks),
                "browser_tasks": len(browser_tasks),
                "total": len(http_tasks) + len(browser_tasks),
            }

        finally:
            try:
                db.close()
            except Exception:
                pass

    except Exception as e:
        logger.exception("Fatal error in scrape_all_companies")
        return {"status": "error", "error": str(e)}


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

        _dispatch_staggered(http_tasks, "scrapers_http")
        _dispatch_staggered(browser_tasks, "scrapers_browser")

        return {
            "status": "dispatched",
            "category": category,
            "http_tasks": len(http_tasks),
            "browser_tasks": len(browser_tasks),
            "total": len(http_tasks) + len(browser_tasks),
        }

    finally:
        db.close()
