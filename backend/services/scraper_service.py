"""
Scraper Service - Orchestration and job saving for custom scrapers.

Provides:
- save_scraped_jobs: Save or update jobs from scrapers
- get_or_create_company: Get or create a company record
- Job deduplication and update logic
"""
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models import Company, Job
from scrapers.base import ScrapedJob
from scrapers.registry import ScraperRegistry
from services.company_resolver import CompanyResolver, normalize_company_key

logger = logging.getLogger(__name__)

# Only save jobs posted within this many days
MAX_JOB_AGE_DAYS = 30


def get_or_create_company(
    db: Session,
    company_slug: str,
    company_name: Optional[str] = None,
    website: Optional[str] = None,
    resolver: Optional[CompanyResolver] = None,
) -> Company:
    """
    Get an existing shared company or create a new one.

    Matches by normalized name (see services.company_resolver), so 'Snap Inc.',
    'snap' and 'Snap' resolve to one row. For registry scrapers the configured
    ScraperConfig.company_name is preferred as the row's name.

    Args:
        db: Database session
        company_slug: Company slug (used when no name is given)
        company_name: Display name (optional)
        website: Company website (optional)
        resolver: Reuse one CompanyResolver across a batch (optional)

    Returns:
        Company record
    """
    name = company_name or company_slug.replace("-", " ").replace("_", " ").title()
    resolver = resolver or CompanyResolver(db)
    metadata = ScraperRegistry.get_metadata(company_slug)
    prefer = metadata["company_name"] if metadata and not company_name else None
    return resolver.get_or_create(name, website=website, prefer_name=prefer or company_name)


# Feeds that list other companies' jobs. Each job carries its real employer in
# raw_data["company_name"]; filing it under the feed ("The Muse") hid the
# employer on every listing.
AGGREGATOR_SLUGS = {"themuse", "remoteok", "arbeitnow"}


def employer_name(company_slug: str, scraped_job: ScrapedJob) -> Optional[str]:
    """The real employer for an aggregator's job, else None (use the feed's company)."""
    if company_slug not in AGGREGATOR_SLUGS:
        return None
    name = ((scraped_job.raw_data or {}).get("company_name") or "").strip()
    return name or None


def employer_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "unknown"


# Column limits on jobs (PostgreSQL enforces them; SQLite silently doesn't).
_MAX_LEN = {"title": 500, "location": 500, "department": 255, "external_job_id": 255}
_INT32_MAX = 2_147_483_647
# Anything before this is a parse artefact (epoch 0, "0001-01-01"), not a real post date.
_MIN_PLAUSIBLE_DATE = datetime(2000, 1, 1)
# New rows are inserted in chunks, each inside its own SAVEPOINT that is released.
_INSERT_CHUNK = 200


@dataclass
class SaveResult:
    """
    Outcome of save_scraped_jobs. Unpacks like the old ``(jobs_new, jobs_updated)``
    tuple so existing callers keep working; the extra counters say why jobs that
    were found did not end up saved.
    """
    new: int = 0
    updated: int = 0
    skipped_old: int = 0       # a real posted_date older than the age cutoff
    skipped_invalid: int = 0   # no title
    duplicates: int = 0        # same id twice in one batch, or unique-index clash
    errors: int = 0            # rows the database rejected
    first_error: Optional[str] = None
    commit_error: Optional[str] = None
    max_age_days: int = MAX_JOB_AGE_DAYS

    def __iter__(self):
        yield self.new
        yield self.updated

    @property
    def saved(self) -> int:
        return self.new + self.updated

    def as_dict(self) -> dict:
        return {
            "new": self.new, "updated": self.updated,
            "skipped_old": self.skipped_old, "skipped_invalid": self.skipped_invalid,
            "duplicates": self.duplicates, "errors": self.errors,
            "first_error": self.first_error, "commit_error": self.commit_error,
        }

    def summary(self) -> str:
        parts = [f"{self.new} new", f"{self.updated} updated"]
        if self.skipped_old:
            parts.append(f"{self.skipped_old} skipped_old (posted > {self.max_age_days}d ago)")
        if self.skipped_invalid:
            parts.append(f"{self.skipped_invalid} skipped_invalid")
        if self.duplicates:
            parts.append(f"{self.duplicates} duplicates")
        if self.errors:
            parts.append(f"{self.errors} errors" + (f" (first: {self.first_error})" if self.first_error else ""))
        if self.commit_error:
            parts.append(f"commit failed: {self.commit_error}")
        return ", ".join(parts)


def _clean_text(value, max_len: Optional[int] = None) -> Optional[str]:
    if value is None:
        return None
    value = str(value).replace("\x00", "")
    if max_len and len(value) > max_len:
        value = value[: max_len - 1].rstrip() + "\u2026"
    return value


def _clean_int(value) -> Optional[int]:
    try:
        value = int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
    if value is None or not (0 < value <= _INT32_MAX):
        return None
    return value


def _clean_date(value) -> Optional[datetime]:
    """Naive UTC datetime, or None when unknown/implausible (never 'ancient')."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        try:  # a bare date
            value = datetime(value.year, value.month, value.day)
        except Exception:
            return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    if value < _MIN_PLAUSIBLE_DATE:
        return None
    return value


def _clean_external_id(value: str) -> str:
    value = _clean_text(value) or ""
    if len(value) > _MAX_LEN["external_job_id"]:
        value = hashlib.md5(value.encode()).hexdigest()
    return value


def _max_job_age_days(db: Session) -> int:
    """The admin-configured job age filter (settings), else MAX_JOB_AGE_DAYS."""
    try:
        from models import AppSetting
        row = db.query(AppSetting.value).filter(AppSetting.key == "max_job_age_days").first()
        return int(row[0]) if row and row[0] else MAX_JOB_AGE_DAYS
    except Exception:
        return MAX_JOB_AGE_DAYS


def _insert_jobs(db: Session, rows: list[dict], stats: SaveResult) -> None:
    """
    Insert new jobs chunk by chunk. Each chunk runs in a SAVEPOINT that is
    released on success (``with db.begin_nested()``); a failing chunk is retried
    row by row so one bad row costs one job, not the batch.

    The old code opened ``db.begin_nested()`` per job and never released it, so
    savepoints nested one inside the next. SQLAlchemy commits nested
    transactions recursively, and past a few hundred new jobs the final
    ``db.commit()`` raised "maximum recursion depth exceeded" - which
    save_scraped_jobs swallowed and returned (0, 0). That is why Google,
    Microsoft, Oracle, IBM and Apple found thousands of jobs and saved none.
    """
    for i in range(0, len(rows), _INSERT_CHUNK):
        chunk = rows[i:i + _INSERT_CHUNK]
        try:
            with db.begin_nested():
                db.add_all([Job(**r) for r in chunk])
                db.flush()
            stats.new += len(chunk)
            continue
        except Exception as e:
            logger.info(f"Chunk insert failed ({type(e).__name__}); retrying {len(chunk)} rows one by one")
        for r in chunk:
            try:
                with db.begin_nested():
                    db.add(Job(**r))
                    db.flush()
                stats.new += 1
            except IntegrityError:
                stats.duplicates += 1
            except Exception as e:
                stats.errors += 1
                if stats.first_error is None:
                    stats.first_error = f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
                logger.warning(f"Database error saving job {r.get('external_job_id')!r}: {e}")


def save_scraped_jobs(
    db: Session,
    company_slug: str,
    jobs: list[ScrapedJob],
) -> SaveResult:
    """
    Save or update scraped jobs in the database.

    Jobs are matched by external_job_id within the company (by feed + id for
    aggregators). New jobs are created, existing jobs are updated with fresh
    data. Jobs with a real posted_date older than the configured age are
    skipped; a missing posted_date means "unknown" and the job is kept.

    Returns a SaveResult, which unpacks as ``(jobs_new, jobs_updated)`` and
    carries per-reason skip counts.
    """
    stats = SaveResult()
    if not jobs:
        return stats

    # Get scraper metadata for company info
    metadata = ScraperRegistry.get_metadata(company_slug)
    company_name = metadata["company_name"] if metadata else None
    careers_url = metadata["careers_url"] if metadata else None

    # Get or create company (normalized-name match; one resolver for the batch)
    resolver = CompanyResolver(db)
    company = get_or_create_company(
        db,
        company_slug,
        company_name=company_name,
        website=careers_url,
        resolver=resolver,
    )

    stats.max_age_days = _max_job_age_days(db)
    cutoff_date = datetime.utcnow() - timedelta(days=stats.max_age_days)
    aggregator = company_slug in AGGREGATOR_SLUGS

    # 1. Validate and normalize every job; drop in-batch duplicates.
    prepared = []
    seen: set[str] = set()
    for scraped_job in jobs:
        try:
            title = _clean_text((scraped_job.title or "").strip(), _MAX_LEN["title"])
            if not title:
                stats.skipped_invalid += 1
                continue
            posted = _clean_date(scraped_job.posted_date)
            if posted is not None and posted < cutoff_date:
                stats.skipped_old += 1
                continue
            external_id = _clean_external_id(scraped_job.external_job_id or scraped_job.generate_id())
            if external_id in seen:
                stats.duplicates += 1
                continue
            seen.add(external_id)
            prepared.append((scraped_job, external_id, {
                "title": title,
                "location": _clean_text(scraped_job.location, _MAX_LEN["location"]),
                "job_url": _clean_text(scraped_job.job_url),
                "job_description": _clean_text(scraped_job.job_description),
                "department": _clean_text(scraped_job.department, _MAX_LEN["department"]),
                "posted_date": posted,
                "salary_min": _clean_int(scraped_job.salary_min),
                "salary_max": _clean_int(scraped_job.salary_max),
            }))
        except Exception as e:
            stats.errors += 1
            stats.first_error = stats.first_error or f"{type(e).__name__}: {e}"[:200]
            logger.error(f"Error preparing job '{getattr(scraped_job, 'title', '?')}': {e}")

    # 2. Existing rows in a few IN queries instead of one query per job.
    existing_by_id: dict[str, Job] = {}
    ids = [ext for _, ext, _ in prepared]
    for i in range(0, len(ids), 500):
        q = db.query(Job).filter(Job.external_job_id.in_(ids[i:i + 500]))
        q = q.filter(Job.source == company_slug) if aggregator else q.filter(Job.company_id == company.id)
        for row in q.all():
            existing_by_id.setdefault(row.external_job_id, row)

    # 3. Update existing rows, collect new ones.
    employer_cache: dict = {}
    new_rows: list[dict] = []
    now = datetime.utcnow()
    for scraped_job, external_id, fields in prepared:
        try:
            # An aggregator's job goes under its real employer. Rows already filed
            # under the feed are matched by feed + id, so they're moved, not duplicated.
            job_company = company
            employer = employer_name(company_slug, scraped_job)
            if employer:
                if employer not in employer_cache:
                    employer_cache[employer] = get_or_create_company(
                        db, employer_slug(employer), company_name=employer, resolver=resolver
                    )
                job_company = employer_cache[employer]

            existing = existing_by_id.get(external_id)
            if existing is not None:
                existing.title = fields["title"]
                existing.company_id = job_company.id
                existing.location = fields["location"] or existing.location
                existing.job_url = fields["job_url"]
                existing.job_description = fields["job_description"] or existing.job_description
                existing.department = fields["department"] or existing.department
                existing.posted_date = fields["posted_date"] or existing.posted_date
                existing.salary_min = fields["salary_min"] or existing.salary_min
                existing.salary_max = fields["salary_max"] or existing.salary_max
                existing.is_active = True  # Mark as still active
                existing.updated_at = now
                stats.updated += 1
            else:
                new_rows.append({
                    **fields,
                    "company_id": job_company.id,
                    "source": company_slug,
                    "external_job_id": external_id,
                    "is_active": True,
                    "status": "wishlist",
                    "date_found": now.date(),
                })
        except Exception as e:
            stats.errors += 1
            stats.first_error = stats.first_error or f"{type(e).__name__}: {e}"[:200]
            logger.error(f"Error saving job '{fields.get('title')}': {e}")

    # 4. Insert new rows (released savepoints; see _insert_jobs).
    try:
        _insert_jobs(db, new_rows, stats)
    except Exception as e:  # e.g. the connection dropped
        stats.errors += len(new_rows) - stats.new
        stats.first_error = stats.first_error or f"{type(e).__name__}: {e}"[:200]
        logger.error(f"Inserting jobs for {company_slug} failed: {e}")

    # Commit with error handling
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit jobs for {company_slug}: {type(e).__name__}: {e}")
        try:
            db.rollback()
        except Exception:
            pass
        stats.commit_error = f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"
        stats.new = stats.updated = 0
        return stats

    log = logger.warning if (stats.saved == 0 and len(jobs) > 0) else logger.info
    log(f"Saved jobs for {company_slug} ({len(jobs)} found): {stats.summary()}")
    return stats


def mark_jobs_inactive(
    db: Session,
    company_slug: str,
    active_external_ids: set[str],
):
    """
    Mark jobs that are no longer on the career page as inactive.

    Args:
        db: Database session
        company_slug: Company slug
        active_external_ids: Set of external IDs still active
    """
    # Get company
    metadata = ScraperRegistry.get_metadata(company_slug)
    if not metadata:
        return

    company = CompanyResolver(db).find(metadata["company_name"], prefer_name=metadata["company_name"])

    if not company:
        return

    # Find jobs to mark inactive
    inactive_count = db.query(Job).filter(
        Job.company_id == company.id,
        Job.source == company_slug,
        Job.is_active == True,
        ~Job.external_job_id.in_(active_external_ids),
    ).update({"is_active": False}, synchronize_session=False)

    db.commit()

    if inactive_count:
        logger.info(f"Marked {inactive_count} jobs inactive for {company_slug}")


def get_scraper_stats(db: Session, company_slug: str) -> dict:
    """
    Get statistics for a scraper.

    Args:
        db: Database session
        company_slug: Company slug

    Returns:
        Dict with statistics
    """
    from models import ScraperRun, ScraperConfigDB

    config = db.query(ScraperConfigDB).filter(
        ScraperConfigDB.company_slug == company_slug
    ).first()

    # Get recent runs
    recent_runs = db.query(ScraperRun).filter(
        ScraperRun.company_slug == company_slug
    ).order_by(ScraperRun.run_at.desc()).limit(10).all()

    # Get job counts
    metadata = ScraperRegistry.get_metadata(company_slug)
    company_name = metadata["company_name"] if metadata else company_slug

    company = CompanyResolver(db).find(company_name, prefer_name=company_name)

    active_jobs = 0
    total_jobs = 0
    if company:
        active_jobs = db.query(Job).filter(
            Job.company_id == company.id,
            Job.is_active == True,
        ).count()
        total_jobs = db.query(Job).filter(
            Job.company_id == company.id,
        ).count()

    # Get last error from most recent failed run
    last_error = last_error_type = None
    for run in recent_runs:
        if not run.success and run.error_message:
            last_error, last_error_type = run.error_message, run.error_type
            break

    return {
        "company_slug": company_slug,
        "company_name": company_name,
        "is_enabled": config.is_enabled if config else True,
        "consecutive_failures": config.consecutive_failures if config else 0,
        "total_runs": config.total_runs if config else 0,
        "last_success_at": config.last_success_at.isoformat() if config and config.last_success_at else None,
        "last_failure_at": config.last_failure_at.isoformat() if config and config.last_failure_at else None,
        "last_error": last_error,
        "last_error_type": last_error_type,
        "active_jobs": active_jobs,
        "total_jobs": total_jobs,
        "recent_runs": [
            {
                "id": run.id,
                "success": run.success,
                "jobs_found": run.jobs_found,
                "duration_seconds": run.duration_seconds,
                "error_message": run.error_message,
                "run_at": run.run_at.isoformat() if run.run_at else None,
            }
            for run in recent_runs
        ],
    }


def get_all_scraper_stats(
    db: Session,
    company_slugs: list[str],
    names: Optional[dict[str, str]] = None,
) -> list[dict]:
    """
    Bulk version of get_scraper_stats for many scrapers (no recent_runs list).

    Uses a constant number of queries regardless of how many scrapers exist:
      1. scraper_configs WHERE company_slug IN (...)
      2. companies whose lower(name) matches a scraper's company name
      3. job counts (total / active) GROUP BY company_id
      4. last error among each scraper's 10 most recent runs (window function,
         supported by PostgreSQL and SQLite >= 3.25)

    Returns dicts in the same order as ``company_slugs`` with the same keys as
    get_scraper_stats (minus "recent_runs").
    """
    from sqlalchemy import case, func
    from models import ScraperRun, ScraperConfigDB

    if not company_slugs:
        return []

    # 1. Configs
    configs = {
        c.company_slug: c
        for c in db.query(ScraperConfigDB).filter(
            ScraperConfigDB.company_slug.in_(company_slugs)
        ).all()
    }

    # Company display names from the registry (in-memory), unless given
    # (disabled scrapers aren't in the registry's metadata).
    names = dict(names or {})
    for slug in company_slugs:
        if slug not in names:
            metadata = ScraperRegistry.get_metadata(slug)
            names[slug] = metadata["company_name"] if metadata else slug

    # 2. Normalized company key -> id among shared companies. Exact-name rows
    #    win over other spellings, then the lowest id ('Snap Inc.' and 'snap'
    #    both count for the Snap scraper until merge_duplicate_companies runs).
    wanted = {normalize_company_key(n): n for n in names.values() if n}
    company_ids: dict[str, int] = {}
    exact: set[str] = set()
    if wanted:
        rows = db.query(Company.id, Company.name).filter(
            Company.user_id.is_(None)
        ).order_by(Company.id).all()
        for cid, cname in rows:
            key = normalize_company_key(cname)
            if key not in wanted:
                continue
            if cname == wanted[key] and key not in exact:
                company_ids[key] = cid
                exact.add(key)
            else:
                company_ids.setdefault(key, cid)

    # 3. Job counts per company
    job_counts: dict[int, tuple[int, int]] = {}
    ids = sorted(set(company_ids.values()))
    if ids:
        rows = db.query(
            Job.company_id,
            func.count(Job.id),
            func.sum(case((Job.is_active == True, 1), else_=0)),  # noqa: E712
        ).filter(Job.company_id.in_(ids)).group_by(Job.company_id).all()
        for cid, total, active in rows:
            job_counts[cid] = (int(total or 0), int(active or 0))

    # 4. Last error among the 10 most recent runs of each scraper
    ranked = db.query(
        ScraperRun.company_slug.label("slug"),
        ScraperRun.success.label("success"),
        ScraperRun.error_message.label("error_message"),
        ScraperRun.error_type.label("error_type"),
        func.row_number().over(
            partition_by=ScraperRun.company_slug,
            order_by=ScraperRun.run_at.desc(),
        ).label("rn"),
    ).filter(ScraperRun.company_slug.in_(company_slugs)).subquery()

    last_errors: dict[str, tuple] = {}
    rows = db.query(ranked.c.slug, ranked.c.error_message, ranked.c.error_type).filter(
        ranked.c.rn <= 10,
        ranked.c.success == False,  # noqa: E712
        ranked.c.error_message.isnot(None),
        ranked.c.error_message != "",
    ).order_by(ranked.c.slug, ranked.c.rn).all()
    for slug, message, error_type in rows:
        last_errors.setdefault(slug, (message, error_type))

    results = []
    for slug in company_slugs:
        config = configs.get(slug)
        company_name = names[slug]
        cid = company_ids.get(normalize_company_key(company_name)) if company_name else None
        total_jobs, active_jobs = job_counts.get(cid, (0, 0)) if cid else (0, 0)
        results.append({
            "company_slug": slug,
            "company_name": company_name,
            "is_enabled": config.is_enabled if config else True,
            "consecutive_failures": config.consecutive_failures if config else 0,
            "total_runs": config.total_runs if config else 0,
            "last_success_at": config.last_success_at.isoformat() if config and config.last_success_at else None,
            "last_failure_at": config.last_failure_at.isoformat() if config and config.last_failure_at else None,
            "last_error": last_errors.get(slug, (None, None))[0],
            "last_error_type": last_errors.get(slug, (None, None))[1],
            "active_jobs": active_jobs,
            "total_jobs": total_jobs,
        })
    return results
