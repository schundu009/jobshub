"""
Celery Tasks for Maintenance Operations.

Tasks:
- cleanup_old_scraper_runs: Remove old scraper run records
- mark_stale_jobs_inactive: Mark jobs not seen recently as inactive
- compute_relevance_scores: Recompute relevance scores for new jobs
- fetch_missing_descriptions: Fetch descriptions for jobs that have empty ones
"""

import logging
import time
from datetime import datetime, timedelta
from sqlalchemy import or_

from celery_app import celery_app
from database import SessionLocal
from models import ScraperRun, Job, ScraperConfigDB
from services import ingestion_service

logger = logging.getLogger(__name__)


def get_db():
    """Get a database session."""
    return SessionLocal()


@celery_app.task
def cleanup_old_scraper_runs(days: int = 30) -> dict:
    """
    Clean up scraper run records older than specified days.

    Args:
        days: Number of days to keep records (default: 30)

    Returns:
        Dict with cleanup results
    """
    logger.info(f"Cleaning up scraper runs older than {days} days")

    db = get_db()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Count records to delete
        count = db.query(ScraperRun).filter(
            ScraperRun.run_at < cutoff
        ).count()

        # Delete old records
        db.query(ScraperRun).filter(
            ScraperRun.run_at < cutoff
        ).delete()

        db.commit()

        logger.info(f"Deleted {count} old scraper run records")

        return {
            "status": "success",
            "deleted_count": count,
            "cutoff_date": cutoff.isoformat(),
        }

    except Exception as e:
        logger.exception("Error cleaning up old scraper runs")
        db.rollback()
        return {
            "status": "error",
            "error": str(e),
        }

    finally:
        db.close()


@celery_app.task
def mark_stale_jobs_inactive(days: int = 14) -> dict:
    """
    Mark jobs not seen in recent scrapes as inactive.

    Jobs from custom scrapers that haven't been updated in the
    specified number of days are marked as inactive (likely removed
    from the company's career page).

    Args:
        days: Number of days without update to consider stale (default: 14)

    Returns:
        Dict with results
    """
    logger.info(f"Marking jobs not updated in {days} days as inactive")

    db = get_db()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)

        # Find jobs from scrapers (source is the company slug, not 'manual')
        # that haven't been updated and are still marked active
        count = db.query(Job).filter(
            Job.source != "manual",
            Job.is_active == True,
            Job.updated_at < cutoff,
        ).update({"is_active": False})

        db.commit()

        logger.info(f"Marked {count} stale jobs as inactive")

        return {
            "status": "success",
            "marked_inactive": count,
            "cutoff_date": cutoff.isoformat(),
        }

    except Exception as e:
        logger.exception("Error marking stale jobs")
        db.rollback()
        return {
            "status": "error",
            "error": str(e),
        }

    finally:
        db.close()


@celery_app.task
def reset_failed_scrapers(threshold: int = 5) -> dict:
    """
    Reset consecutive failure count for scrapers that have been failing.

    This is useful for manual intervention after fixing scraper issues.

    Args:
        threshold: Only reset scrapers with failures >= threshold

    Returns:
        Dict with results
    """
    logger.info(f"Resetting scrapers with >= {threshold} consecutive failures")

    db = get_db()
    try:
        count = db.query(ScraperConfigDB).filter(
            ScraperConfigDB.consecutive_failures >= threshold
        ).update({"consecutive_failures": 0})

        db.commit()

        logger.info(f"Reset failure count for {count} scrapers")

        return {
            "status": "success",
            "reset_count": count,
        }

    except Exception as e:
        logger.exception("Error resetting failed scrapers")
        db.rollback()
        return {
            "status": "error",
            "error": str(e),
        }

    finally:
        db.close()


@celery_app.task
def generate_scraper_health_report() -> dict:
    """
    Generate a health report for all scrapers.

    Returns:
        Dict with scraper health information
    """
    logger.info("Generating scraper health report")

    db = get_db()
    try:
        configs = db.query(ScraperConfigDB).all()

        healthy = []
        warning = []
        critical = []

        for config in configs:
            status = {
                "company_slug": config.company_slug,
                "is_enabled": config.is_enabled,
                "consecutive_failures": config.consecutive_failures,
                "total_runs": config.total_runs,
                "total_jobs_found": config.total_jobs_found,
                "last_success_at": config.last_success_at.isoformat() if config.last_success_at else None,
                "last_failure_at": config.last_failure_at.isoformat() if config.last_failure_at else None,
            }

            if not config.is_enabled:
                continue
            elif config.consecutive_failures >= 5:
                critical.append(status)
            elif config.consecutive_failures >= 2:
                warning.append(status)
            else:
                healthy.append(status)

        report = {
            "generated_at": datetime.utcnow().isoformat(),
            "summary": {
                "healthy": len(healthy),
                "warning": len(warning),
                "critical": len(critical),
                "total": len(healthy) + len(warning) + len(critical),
            },
            "healthy": healthy,
            "warning": warning,
            "critical": critical,
        }

        logger.info(
            f"Health report: {len(healthy)} healthy, "
            f"{len(warning)} warning, {len(critical)} critical"
        )

        return report

    finally:
        db.close()


@celery_app.task
def check_scraper_health_and_notify() -> dict:
    """
    Check scraper health and send email alert if too many failures
    or no new jobs in the last 24 hours.
    """
    import os
    logger.info("Running scraper health check with notification")

    db = get_db()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=24)

        # Count recent runs
        from sqlalchemy import func
        total_runs = db.query(func.count(ScraperRun.id)).filter(ScraperRun.started_at > cutoff).scalar() or 0
        success_runs = db.query(func.count(ScraperRun.id)).filter(ScraperRun.started_at > cutoff, ScraperRun.success == True).scalar() or 0
        new_jobs = db.query(func.coalesce(func.sum(ScraperRun.jobs_new), 0)).filter(ScraperRun.started_at > cutoff, ScraperRun.success == True).scalar() or 0
        active_jobs = db.query(func.count(Job.id)).filter(Job.is_active == True).scalar() or 0

        success_rate = (success_runs / max(total_runs, 1)) * 100
        is_healthy = success_rate >= 50 and new_jobs > 0 and total_runs > 0

        report = {
            "total_runs_24h": total_runs,
            "success_runs_24h": success_runs,
            "success_rate": round(success_rate, 1),
            "new_jobs_24h": int(new_jobs),
            "active_jobs": active_jobs,
            "is_healthy": is_healthy,
            "checked_at": datetime.utcnow().isoformat(),
        }

        # Get top failures for detail
        recent_fails = db.query(ScraperRun).filter(
            ScraperRun.started_at > cutoff, ScraperRun.success == False
        ).order_by(ScraperRun.started_at.desc()).limit(10).all()
        fail_details = "\n".join(
            f"  - {r.company_slug}: {(r.error_message or 'unknown')[:60]}"
            for r in recent_fails
        )

        # Get top successes
        recent_success = db.query(ScraperRun).filter(
            ScraperRun.started_at > cutoff, ScraperRun.success == True, ScraperRun.jobs_new > 0
        ).order_by(ScraperRun.jobs_new.desc()).limit(5).all()
        success_details = "\n".join(
            f"  - {r.company_slug}: {r.jobs_found} found, {r.jobs_new} new"
            for r in recent_success
        )

        alert_email = os.environ.get("ALERT_EMAIL", "chundubabu@gmail.com")

        if not is_healthy:
            subject = f"[ALERT] Cariara Scraper {'DOWN' if total_runs == 0 else 'DEGRADED'} — {success_rate:.0f}% success"
            body = (
                f"Scraper Health Alert\n"
                f"====================\n\n"
                f"Status: {'NO SCRAPES RAN' if total_runs == 0 else 'HIGH FAILURE RATE' if success_rate < 50 else 'NO NEW JOBS'}\n"
                f"Success rate: {success_rate:.0f}% ({success_runs}/{total_runs})\n"
                f"New jobs (last 6h): {int(new_jobs)}\n"
                f"Active jobs total: {active_jobs}\n"
                f"Time: {datetime.utcnow().isoformat()}\n\n"
                f"Recent failures:\n{fail_details}\n\n"
                f"Action: Check Railway logs → cariara-worker\n"
            )
            _send_alert_email(alert_email, subject, body)
            logger.warning(f"Scraper health alert sent: {subject}")
        else:
            # Send success summary too so you know it's working
            subject = f"[OK] Cariara Scraper Healthy — {int(new_jobs)} new jobs, {success_rate:.0f}% success"
            body = (
                f"Scraper Health Report\n"
                f"=====================\n\n"
                f"Status: HEALTHY\n"
                f"Success rate: {success_rate:.0f}% ({success_runs}/{total_runs})\n"
                f"New jobs (last 6h): {int(new_jobs)}\n"
                f"Active jobs total: {active_jobs}\n"
                f"Time: {datetime.utcnow().isoformat()}\n\n"
                f"Top scrapers:\n{success_details}\n"
            )
            _send_alert_email(alert_email, subject, body)
            logger.info(f"Scrapers healthy: {success_rate:.0f}% success, {int(new_jobs)} new jobs")

        return report
    finally:
        db.close()


def _send_alert_email(to_email: str, subject: str, body: str):
    """Send alert email via SMTP or log if not configured."""
    import os
    import smtplib
    from email.mime.text import MIMEText

    smtp_host = os.environ.get("SMTP_HOST")
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")

    if not smtp_host:
        # Fallback: just log the alert
        logger.error(f"EMAIL ALERT (SMTP not configured): {subject}\n{body}")
        return

    try:
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_user or "alerts@cariara.com"
        msg["To"] = to_email

        with smtplib.SMTP(smtp_host, int(os.environ.get("SMTP_PORT", 587))) as server:
            server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        logger.info(f"Alert email sent to {to_email}")
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")


@celery_app.task
def fetch_missing_descriptions(batch_size: int = 200, delay_between: float = 0.5) -> dict:
    """
    Fetch descriptions for jobs that have empty or missing descriptions.

    This task queries jobs with empty descriptions that have a valid job_url,
    fetches the description from the job page, and updates the record.

    Args:
        batch_size: Maximum number of jobs to process per run (default: 200;
            200 x ~(fetch + 0.5s) fits the 25-minute soft time limit)
        delay_between: Seconds to wait between requests to avoid rate limiting (default: 0.5)

    Returns:
        Dict with fetch results
    """
    logger.info(f"Fetching missing descriptions for up to {batch_size} jobs")

    db = get_db()
    try:
        from services import app_settings
        if not app_settings.get_bool(db, app_settings.DESCRIPTION_FETCH_ENABLED_KEY, True):
            logger.info("fetch_missing_descriptions skipped: description_fetch_enabled=false")
            return {"status": "skipped", "reason": "description_fetch_disabled"}

        # Find ALL jobs with missing descriptions that have a valid URL
        jobs_to_update = db.query(Job).filter(
            Job.is_active == True,
            Job.job_url.isnot(None),
            Job.job_url != '',
            or_(
                Job.job_description.is_(None),
                Job.job_description == '',
                Job.job_description == 'No description available.'
            )
        ).limit(batch_size).all()

        if not jobs_to_update:
            logger.info("No jobs with missing descriptions found")
            return {
                "status": "success",
                "processed": 0,
                "updated": 0,
                "failed": 0,
                "message": "No jobs with missing descriptions"
            }

        logger.info(f"Found {len(jobs_to_update)} jobs with missing descriptions")

        updated_count = 0
        failed_count = 0
        failed_jobs = []

        for job in jobs_to_update:
            try:
                logger.debug(f"Fetching description for job {job.id}: {job.title} at {job.job_url}")

                description = ingestion_service.fetch_job_description_from_url(job.job_url)

                if description and len(description) > 100:
                    job.job_description = description[:15000]
                    job.updated_at = datetime.utcnow()
                    db.commit()
                    updated_count += 1
                    logger.info(f"Updated description for job {job.id}: {job.title} ({len(description)} chars)")
                else:
                    failed_count += 1
                    failed_jobs.append({
                        "id": job.id,
                        "title": job.title,
                        "url": job.job_url,
                        "reason": "Empty or short description returned"
                    })
                    logger.warning(f"Could not fetch description for job {job.id}: {job.title}")

                # Rate limiting between requests
                time.sleep(delay_between)

            except Exception as e:
                failed_count += 1
                failed_jobs.append({
                    "id": job.id,
                    "title": job.title,
                    "url": job.job_url,
                    "reason": str(e)
                })
                logger.error(f"Error fetching description for job {job.id}: {e}")
                db.rollback()

        result = {
            "status": "success",
            "processed": len(jobs_to_update),
            "updated": updated_count,
            "failed": failed_count,
            "failed_jobs": failed_jobs[:10] if failed_jobs else [],  # Limit failed jobs in response
        }

        logger.info(f"Description fetch complete: {updated_count} updated, {failed_count} failed")

        return result

    except Exception as e:
        logger.exception("Error in fetch_missing_descriptions task")
        return {
            "status": "error",
            "error": str(e),
        }

    finally:
        db.close()


# ATS board URL patterns: (ats, regex capturing the board token, URL template).
_ATS_BOARD_PATTERNS = {
    "greenhouse": (
        r"boards-api\.greenhouse\.io/v1/boards/([^/?#]+)",
        "https://boards-api.greenhouse.io/v1/boards/{token}/jobs",
    ),
    "ashby": (
        r"api\.ashbyhq\.com/posting-api/job-board/([^/?#]+)",
        "https://api.ashbyhq.com/posting-api/job-board/{token}",
    ),
    "lever": (
        r"api\.lever\.co/v0/postings/([^/?#]+)",
        "https://api.lever.co/v0/postings/{token}?mode=json",
    ),
}


def _scraper_ats(scraper_cls) -> str | None:
    """ATS of a registry scraper from its mixin (isinstance on the class MRO)."""
    try:
        from scrapers.custom.remaining_scrapers import (
            AshbyMixin, GreenhouseMixin, LeverMixin, SmartRecruitersMixin, WorkdayMixin,
        )
    except Exception:
        return None
    for mixin, ats in (
        (GreenhouseMixin, "greenhouse"),
        (AshbyMixin, "ashby"),
        (LeverMixin, "lever"),
        (SmartRecruitersMixin, "smartrecruiters"),
        (WorkdayMixin, "workday"),
    ):
        if issubclass(scraper_cls, mixin):
            return ats
    return None


def _honors_url_override(scraper_cls) -> bool:
    """Only scrapers whose scrape() goes through resolve_api_url() read config_overrides.url_override."""
    import inspect
    try:
        return "resolve_api_url" in inspect.getsource(scraper_cls.scrape)
    except (OSError, TypeError):
        return False


def _board_token(ats: str, api_url: str | None) -> str | None:
    import re
    if not api_url or ats not in _ATS_BOARD_PATTERNS:
        return None
    match = re.search(_ATS_BOARD_PATTERNS[ats][0], api_url)
    return match.group(1) if match else None


def _token_variants(token: str) -> list[str]:
    """Plausible renames of the same company's board token (never a different company)."""
    base = token.lower()
    stripped = base
    for suffix in ("-inc", "inc", "-usa", "usa", "hq", "-hq", "careers", "jobs"):
        if stripped.endswith(suffix) and len(stripped) > len(suffix) + 2:
            stripped = stripped[: -len(suffix)]
            break
    variants = [
        base, stripped, stripped + "inc", stripped + "-inc", stripped + "usa",
        stripped + "hq", stripped + "careers", stripped + "jobs",
        stripped.replace("-", ""), stripped.replace("-", "") + "ai",
    ]
    seen: set = set()
    return [v for v in variants if v and not (v in seen or seen.add(v))]


def _similar_board(token: str, variant: str, company_name: str) -> bool:
    """
    Guard against adopting another company's board: the variant must share
    its core with the current token or with the company's normalized name.
    """
    from services.company_resolver import normalize_company_key
    import re

    def core(value: str) -> str:
        return re.sub(r"(inc|usa|hq|careers|jobs|ai)$", "", re.sub(r"[^a-z0-9]", "", value.lower()))

    v = core(variant)
    if len(v) < 3:
        return False
    return v in (core(token), core(normalize_company_key(company_name)))


def _probe_board(ats: str, url: str) -> int:
    """Number of postings on a board URL (0 if missing/empty/unreachable)."""
    import httpx
    try:
        r = httpx.get(url, timeout=8, follow_redirects=True)
        if r.status_code != 200:
            return 0
        data = r.json()
    except Exception as e:
        logger.debug(f"auto_heal probe {url} error: {e}")
        return 0
    if isinstance(data, list):  # Lever
        return len(data)
    if isinstance(data, dict) and isinstance(data.get("jobs"), list):  # Greenhouse, Ashby
        return len(data["jobs"])
    return 0


@celery_app.task(name="tasks.maintenance_tasks.auto_heal_scrapers")
def auto_heal_scrapers() -> dict:
    """
    Auto-heal Greenhouse scrapers failing because their board token changed.

    For each enabled scraper with >= 3 consecutive failures:
    - the ATS comes from the scraper class's mixin; anything that isn't a
      GreenhouseMixin scraper is skipped entirely (reported, never touched)
    - variants of the scraper's *current* board token are probed on that same
      ATS only; a variant must resemble the token or the company name and the
      board must have postings (never adopt another company's board)
    - a working URL is written to config_overrides.url_override (no deploy
      needed) and failures reset, but only if the scraper reads url_override;
      otherwise the URL is reported as a suggestion and failures are kept
    - after 10 failures with no fix, the scraper is disabled
    """
    from scrapers.registry import ScraperRegistry

    logger.info("Running auto_heal_scrapers")

    healed = []
    suggested = []
    disabled = []
    unresolved = []

    db = get_db()
    try:
        candidates = db.query(ScraperConfigDB).filter(
            ScraperConfigDB.consecutive_failures >= 3,
            ScraperConfigDB.is_enabled == True,  # noqa: E712
        ).all()

        logger.info(f"auto_heal_scrapers: {len(candidates)} scrapers to inspect")

        for cfg in candidates:
            slug = cfg.company_slug
            overrides = cfg.config_overrides or {}
            scraper_cls = ScraperRegistry.get(slug)
            if scraper_cls is None:
                unresolved.append({"slug": slug, "reason": "not in registry"})
                continue

            ats = _scraper_ats(scraper_cls)
            if ats != "greenhouse":
                # Only Greenhouse scrapers read url_override; ScraperConfigDB's
                # scraper_type defaulted to "greenhouse" for everything, so the
                # class mixin is the source of truth. Leave others alone.
                unresolved.append({"slug": slug, "failures": cfg.consecutive_failures,
                                   "reason": f"ats={ats or 'unknown'}; auto-heal handles Greenhouse only"})
                continue
            api_url = getattr(scraper_cls, "API_URL", None) or getattr(scraper_cls.config, "api_url", None)
            token = _board_token(ats, api_url) if ats else None

            found_url = None
            if token:
                current_override = overrides.get("url_override")
                template = _ATS_BOARD_PATTERNS[ats][1]
                for variant in _token_variants(token):
                    if not _similar_board(token, variant, scraper_cls.config.company_name):
                        continue
                    url = template.format(token=variant)
                    if url == current_override:
                        continue
                    if _probe_board(ats, url) > 0:
                        found_url = url
                        logger.info(f"auto_heal: {slug} ({ats}) -> working board '{variant}'")
                        break

            if found_url and _honors_url_override(scraper_cls):
                new_overrides = {**overrides, "url_override": found_url}
                new_overrides.pop("auto_disabled", None)
                new_overrides.pop("auto_disabled_reason", None)
                cfg.config_overrides = new_overrides
                cfg.consecutive_failures = 0
                db.commit()
                healed.append({"slug": slug, "ats": ats, "url": found_url})
                continue

            if found_url:
                # The scraper ignores url_override (only Greenhouse reads it today):
                # report the fix instead of pretending it's healed.
                suggested.append({"slug": slug, "ats": ats, "url": found_url,
                                  "reason": "update API_URL in the scraper"})
            last_error_type = db.query(ScraperRun.error_type).filter(
                ScraperRun.company_slug == slug
            ).order_by(ScraperRun.run_at.desc(), ScraperRun.id.desc()).limit(1).scalar()
            if cfg.consecutive_failures >= 10 and last_error_type == "empty_result":
                # A board that answers with 0 jobs isn't disabled on that alone.
                unresolved.append({"slug": slug, "failures": cfg.consecutive_failures,
                                   "reason": "empty_result streak; not auto-disabled"})
            elif cfg.consecutive_failures >= 10:
                cfg.config_overrides = {
                    **overrides,
                    "auto_disabled": True,
                    "auto_disabled_reason": (
                        f"{cfg.consecutive_failures} failures; "
                        + (f"suggested board {found_url}" if found_url else f"no working {ats or 'ATS'} board found")
                    ),
                }
                cfg.is_enabled = False
                db.commit()
                disabled.append({"slug": slug, "failures": cfg.consecutive_failures})
                logger.warning(f"auto_heal: disabled {slug} after {cfg.consecutive_failures} failures")
            elif not found_url:
                reason = (
                    f"no working {ats} board among token variants" if token
                    else f"ats={ats or 'unknown'}, manual fix needed"
                )
                unresolved.append({"slug": slug, "failures": cfg.consecutive_failures, "reason": reason})

    except Exception:
        logger.exception("auto_heal_scrapers failed")
        db.rollback()
    finally:
        db.close()

    logger.info(
        f"auto_heal_scrapers done: {len(healed)} healed, {len(suggested)} suggested, "
        f"{len(disabled)} disabled, {len(unresolved)} unresolved"
    )
    return {"healed": healed, "suggested": suggested, "disabled": disabled, "unresolved": unresolved}
