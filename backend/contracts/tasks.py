"""
Celery tasks for contract roles (queue "contracts").

- scrape_all_contracts: fan out one scrape_contract_source per staffing scraper
- scrape_contract_source: scrape one staffing board, save to contract_jobs,
  close postings it no longer lists
- expire_contract_jobs: daily, deactivate roles past contract_max_age_days
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional

from celery_app import celery_app
from database import SessionLocal

logger = logging.getLogger(__name__)

QUEUE = "contracts"


def staffing_slugs() -> list[str]:
    from contracts.scrapers import STAFFING_CATEGORY, load_all
    from scrapers.registry import ScraperRegistry
    load_all()
    return sorted(ScraperRegistry.get_by_category(STAFFING_CATEGORY))


def _record_run(db, slug: str, result, stats, task_id: Optional[str]) -> None:
    from models import ScraperConfigDB, ScraperRun
    note = None
    if stats is not None:
        note = (f"contracts: {stats.new} new, {stats.updated} updated, {stats.skipped_old} skipped_old, "
                f"{stats.skipped_not_contract} not_contract, {stats.errors} errors")[:1000]
    success = bool(result.success) and not (stats is not None and stats.saved == 0 and stats.errors)
    db.add(ScraperRun(
        company_slug=slug, success=success, jobs_found=result.jobs_found or 0,
        jobs_new=stats.new if stats else 0, jobs_updated=stats.updated if stats else 0,
        duration_seconds=result.duration_seconds, started_at=result.started_at,
        completed_at=result.completed_at, error_message=result.error_message or note,
        error_type=getattr(result.error_type, "value", result.error_type) or None, celery_task_id=task_id,
    ))
    config = db.query(ScraperConfigDB).filter(ScraperConfigDB.company_slug == slug).first()
    if not config:
        config = ScraperConfigDB(company_slug=slug)
        db.add(config)
    config.total_runs = (config.total_runs or 0) + 1
    if success:
        config.last_success_at = datetime.utcnow()
        config.consecutive_failures = 0
    else:
        config.last_failure_at = datetime.utcnow()
        config.consecutive_failures = (config.consecutive_failures or 0) + 1
    db.commit()


def scrape_source(db, slug: str, task_id: Optional[str] = None) -> dict:
    """Scrape one staffing board into contract_jobs (sync; used by the task and inline runs)."""
    from contracts.service import deactivate_unseen, save_contract_jobs, _external_id
    from scrapers.rate_limiter import get_rate_limiter
    from scrapers.registry import ScraperRegistry, get_scraper

    staffing_slugs()  # make sure the staffing modules are registered
    scraper = get_scraper(slug, rate_limiter=get_rate_limiter())
    if scraper is None:
        return {"source": slug, "status": "error", "reason": "scraper_not_found"}
    meta = ScraperRegistry.get_metadata(slug) or {}
    result = asyncio.run(scraper.run())
    stats = None
    closed = 0
    if result.success and result.jobs:
        stats = save_contract_jobs(db, slug, result.jobs, source_type="staffing",
                                   agency_name=meta.get("company_name"))
        if stats.errors == 0:
            closed = deactivate_unseen(db, slug, {_external_id(j) for j in result.jobs})
    try:
        _record_run(db, slug, result, stats, task_id)
    except Exception as e:
        logger.warning(f"recording contract run for {slug} failed: {e}")
        db.rollback()
    return {
        "source": slug, "status": "success" if result.success else "failed",
        "found": result.jobs_found, "saved": stats.as_dict() if stats else None,
        "closed": closed, "error": result.error_message,
    }


@celery_app.task(bind=True, max_retries=1, default_retry_delay=120)
def scrape_contract_source(self, slug: str) -> dict:
    db = SessionLocal()
    try:
        return scrape_source(db, slug, task_id=self.request.id)
    finally:
        db.close()


@celery_app.task
def scrape_all_contracts() -> dict:
    slugs = staffing_slugs()
    for i, slug in enumerate(slugs):
        scrape_contract_source.apply_async(args=[slug], queue=QUEUE, countdown=i * 10)
    logger.info(f"Dispatched {len(slugs)} contract scrapes")
    return {"status": "dispatched", "sources": slugs}


@celery_app.task
def expire_contract_jobs() -> dict:
    from contracts.service import expire_contract_jobs as expire
    db = SessionLocal()
    try:
        return {"status": "success", "expired": expire(db)}
    except Exception as e:
        db.rollback()
        logger.exception("expire_contract_jobs failed")
        return {"status": "error", "error": str(e)}
    finally:
        db.close()


def run_all_contracts_inline(db) -> list[dict]:
    """Admin POST /api/contracts/run with APPLY_INLINE_TASKS=1 (local dev)."""
    out = []
    for slug in staffing_slugs():
        try:
            out.append(scrape_source(db, slug))
        except Exception as e:
            db.rollback()
            out.append({"source": slug, "status": "error", "error": f"{type(e).__name__}: {e}"})
    return out
