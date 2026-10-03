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

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError, PendingRollbackError

from models import Company, Job
from scrapers.base import ScrapedJob
from services.it_roles import is_it_role
from services.job_location import job_countries, to_country_codes
from services.job_freshness import (
    REPOST_WINDOW_DAYS, apply_freshness, effective_posted_at, evergreen_status, listed_days, normalize_title,
)
from scrapers.registry import ScraperRegistry
from services.company_resolver import CompanyResolver, normalize_company_key

logger = logging.getLogger(__name__)

# Contract roles are stored by the contracts package (contract_jobs), not in jobs.
def contract_routing(title, description=None, raw=None, staffing=False):
    """The contracts bridge: (route_to_contracts, employment_type) from contracts.classifier."""
    from contracts.classifier import contract_routing as route
    return route(title, description, raw, staffing=staffing)


# Aggregator feeds only: skip jobs posted more than this many days ago
# (company boards keep a posting while it is listed; see save_scraped_jobs).
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
    skipped_old: int = 0       # aggregator feeds only: posted_date older than the age cutoff
    skipped_invalid: int = 0   # no title
    skipped_non_it: int = 0    # confidently not an IT/tech role (services.it_roles)
    duplicates: int = 0        # same id twice in one batch, or unique-index clash
    errors: int = 0            # rows the database rejected
    contracts: int = 0         # contract postings routed to contract_jobs (contracts package)
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
            "skipped_non_it": self.skipped_non_it,
            "duplicates": self.duplicates, "errors": self.errors, "contracts": self.contracts,
            "first_error": self.first_error, "commit_error": self.commit_error,
        }

    def summary(self) -> str:
        parts = [f"{self.new} new", f"{self.updated} updated"]
        if self.skipped_old:
            parts.append(f"{self.skipped_old} skipped_old (posted > {self.max_age_days}d ago)")
        if self.skipped_invalid:
            parts.append(f"{self.skipped_invalid} skipped_invalid")
        if self.skipped_non_it:
            parts.append(f"{self.skipped_non_it} skipped_non_it")
        if self.duplicates:
            parts.append(f"{self.duplicates} duplicates")
        if self.contracts:
            parts.append(f"{self.contracts} routed to contracts")
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
        value = value[: max_len - 1].rstrip() + "…"
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


def is_connection_error(exc: BaseException) -> bool:
    """The DB connection itself is broken - retrying on this session can't work."""
    if isinstance(exc, (OperationalError, PendingRollbackError)):
        return True
    return isinstance(exc, DBAPIError) and bool(getattr(exc, "connection_invalidated", False))


def _rollback(db: Session) -> None:
    """Discard the failed work and start a fresh transaction (a new connection if it broke)."""
    try:
        db.rollback()
    except Exception:
        try:
            db.close()
        except Exception:
            pass


# Consecutive connection-level failures before giving up on the batch (the
# caller, tasks.scraper_tasks.save_jobs_into_result, retries once on a fresh session).
_MAX_CONSECUTIVE_CONN_ERRORS = 3


def _insert_jobs(db: Session, rows: list[dict], stats: SaveResult) -> None:
    """
    Insert new jobs chunk by chunk, committing each chunk. A failing chunk is
    rolled back and retried row by row (each row committed), so one bad row
    costs one job, never the batch - even when the failure invalidated the
    connection ("lost synchronization", PendingRollbackError): the rollback
    starts a fresh transaction on a fresh connection and only uncommitted work
    (that one row) is lost.

    History: per-job ``db.begin_nested()`` savepoints that were never released
    nested ~N deep and the final commit hit "maximum recursion depth exceeded";
    later a single broken row left the session in PendingRollbackError and every
    following row failed (IBM: 289 errors).
    """
    conn_failures = 0
    for i in range(0, len(rows), _INSERT_CHUNK):
        chunk = rows[i:i + _INSERT_CHUNK]
        try:
            db.add_all([Job(**r) for r in chunk])
            db.flush()
            db.commit()
            stats.new += len(chunk)
            conn_failures = 0
            continue
        except Exception as e:
            _rollback(db)
            logger.info(f"Chunk insert failed ({type(e).__name__}); retrying {len(chunk)} rows one by one")
        for r in chunk:
            try:
                db.add(Job(**r))
                db.flush()
                db.commit()
                stats.new += 1
                conn_failures = 0
            except IntegrityError:
                _rollback(db)
                stats.duplicates += 1
            except Exception as e:
                _rollback(db)
                if is_connection_error(e):
                    conn_failures += 1
                    if conn_failures >= _MAX_CONSECUTIVE_CONN_ERRORS:
                        raise  # the database is gone, not this row
                stats.errors += 1
                if stats.first_error is None:
                    stats.first_error = f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
                logger.warning(f"Database error saving job {r.get('external_job_id')!r}: {e}")


# ------------------------------------------------------------------ contracts bridge

def _raw_fields(scraped_job: ScrapedJob) -> dict:
    g = lambda k: getattr(scraped_job, k, None)  # noqa: E731
    return {
        "employment_type_raw": g("employment_type_raw"),
        "employment_type": g("employment_type"),
        "extra": g("extra") or {},
    }


def _route_to_contracts(db: Session, company_slug: str, company_id: Optional[int], source_type: str,
                        jobs: list, detected: dict, agency_name: Optional[str] = None,
                        rollback_on_error: bool = True) -> int:
    """Hand contract postings to the contracts package. Never raises."""
    if not jobs:
        return 0
    try:
        from contracts.service import classify_scraped, save_contract_jobs
        classified = {}
        for j in jobs:
            fields = classify_scraped(j, default_type=None)
            if fields.get("employment_type") is None:
                fields["employment_type"] = detected.get(id(j)) or "contract"
            classified[id(j)] = fields
        result = save_contract_jobs(
            db, company_slug, jobs, source_type=source_type, company_id=company_id,
            agency_name=agency_name, commit=False, classified=classified,
        )
        return result.saved
    except Exception as e:
        logger.warning(f"Routing {len(jobs)} contract postings for {company_slug} failed: {type(e).__name__}: {e}")
        if rollback_on_error:
            _rollback(db)
        return 0


def route_contract_job_data(db: Session, source: str, job_data: dict, company_id: Optional[int],
                            source_type: str = "aggregator") -> bool:
    """
    For the ingest save path (dict-shaped jobs): when the posting is a
    contract role, save it to contract_jobs and return True (the caller skips
    the jobs insert). Does not commit; never raises.
    """
    try:
        title = (job_data.get("title") or "").strip()
        description = job_data.get("job_description") or job_data.get("description") or ""
        raw = {"employment_type_raw": job_data.get("employment_type") or job_data.get("job_type")
               or job_data.get("employment_type_raw")}
        route, et = contract_routing(title, description, raw)
        if not route:
            return False
        posted = job_data.get("posted_date")
        if isinstance(posted, str):
            try:
                from dateutil import parser
                posted = parser.parse(posted)
            except Exception:
                posted = None
        scraped = ScrapedJob(
            title=title, location=job_data.get("location") or "", job_url=job_data.get("job_url") or "",
            external_job_id=str(job_data.get("external_job_id") or ""), job_description=description,
            posted_date=posted if isinstance(posted, datetime) else None,
            employment_type_raw=raw["employment_type_raw"],
        )
        _route_to_contracts(db, source, company_id, source_type, [scraped], {id(scraped): et},
                            rollback_on_error=False)
        return True
    except Exception as e:
        logger.info(f"contract routing check failed for {source}: {e}")
        return False


# -------------------------------------------------------------------------- save

REPOST_REDATE_DAYS = 7  # posted_date moving forward at least this much counts as a repost


def _find_reposts(db: Session, company_ids: set, titles: set, now: datetime) -> dict:
    """(company_id, normalized title) -> max reposted_count among recently closed postings."""
    if not company_ids or not titles:
        return {}
    since = now - timedelta(days=REPOST_WINDOW_DAYS)
    found: dict = {}
    lowered = sorted({t.lower() for t in titles})
    for i in range(0, len(lowered), 500):
        rows = db.query(Job.company_id, Job.title, Job.reposted_count).filter(
            Job.company_id.in_(list(company_ids)),
            Job.is_active == False,  # noqa: E712
            func.lower(Job.title).in_(lowered[i:i + 500]),
            or_(Job.last_seen_at >= since, and_(Job.last_seen_at.is_(None), Job.updated_at >= since)),
        ).all()
        for cid, title, count in rows:
            key = (cid, normalize_title(title))
            found[key] = max(found.get(key, 0), count or 0)
    return found


def save_scraped_jobs(
    db: Session,
    company_slug: str,
    jobs: list[ScrapedJob],
) -> SaveResult:
    """
    Save or update scraped jobs in the database.

    - Jobs are matched by external_job_id within the company (by feed + id for
      aggregators). New jobs are created, existing jobs refreshed.
    - Age: a posting still listed on the employer's own board is kept whatever
      its posted_date (freshness is modelled instead: first_seen_at,
      last_seen_at, effective_posted_at, reposted_count, is_evergreen). Only
      aggregator feeds keep the max_job_age_days cut-off.
    - Contract postings (contracts.classifier) are routed to contract_jobs;
      staffing-category scrapers never write to jobs.

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
    staffing = bool(metadata and metadata.get("category") == "staffing")

    if staffing:
        detected = {id(j): "contract" for j in jobs}
        stats.contracts = _route_to_contracts(db, company_slug, None, "staffing", list(jobs), detected,
                                              agency_name=company_name)
        try:
            db.commit()
        except Exception as e:
            _rollback(db)
            stats.commit_error = f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"
            stats.contracts = 0
        return stats

    # Get or create company (normalized-name match; one resolver for the batch)
    resolver = CompanyResolver(db)
    company = get_or_create_company(
        db,
        company_slug,
        company_name=company_name,
        website=careers_url,
        resolver=resolver,
    )
    company_id = company.id

    stats.max_age_days = _max_job_age_days(db)
    now = datetime.utcnow()
    cutoff_date = now - timedelta(days=stats.max_age_days)
    aggregator = company_slug in AGGREGATOR_SLUGS

    # 1. Validate and normalize every job; drop in-batch duplicates; route contracts.
    prepared = []
    contract_jobs: list = []
    contract_ids: list[str] = []
    detected: dict = {}
    contract_type_by_ext: dict[str, str] = {}
    non_it_ids: list[str] = []
    seen: set[str] = set()
    for scraped_job in jobs:
        try:
            title = _clean_text((scraped_job.title or "").strip(), _MAX_LEN["title"])
            if not title:
                stats.skipped_invalid += 1
                continue
            posted = _clean_date(scraped_job.posted_date)
            external_id = _clean_external_id(scraped_job.external_job_id or scraped_job.generate_id())
            if external_id in seen:
                stats.duplicates += 1
                continue
            seen.add(external_id)
            route, employment_type = contract_routing(title, scraped_job.job_description, _raw_fields(scraped_job))
            if route:
                detected[id(scraped_job)] = employment_type
                contract_type_by_ext[external_id] = employment_type
                contract_jobs.append(scraped_job)
                contract_ids.append(external_id)
                continue
            # IT/tech roles only. A generic title ("Consultant", "Shift Lead")
            # stays only when its department is tech; on 609 labelled titles
            # this keeps recall at 1.0 and precision 0.99 (vs 0.93 keeping them).
            if not is_it_role(title, department=scraped_job.department):
                stats.skipped_non_it += 1
                non_it_ids.append(external_id)
                continue
            if aggregator and posted is not None and posted < cutoff_date:
                stats.skipped_old += 1
                continue
            prepared.append((scraped_job, external_id, {
                "title": title,
                "location": _clean_text(scraped_job.location, _MAX_LEN["location"]),
                "job_url": _clean_text(scraped_job.job_url),
                "job_description": _clean_text(scraped_job.job_description),
                "department": _clean_text(scraped_job.department, _MAX_LEN["department"]),
                "posted_date": posted,
                "salary_min": _clean_int(scraped_job.salary_min),
                "salary_max": _clean_int(scraped_job.salary_max),
                "employment_type": employment_type,
                "country_codes": to_country_codes(job_countries(scraped_job.location, title)),
            }))
        except Exception as e:
            stats.errors += 1
            stats.first_error = stats.first_error or f"{type(e).__name__}: {e}"[:200]
            logger.error(f"Error preparing job '{getattr(scraped_job, 'title', '?')}': {e}")

    # 2. Existing rows in a few IN queries instead of one query per job.
    existing_by_id: dict[str, Job] = {}
    ids = [ext for _, ext, _ in prepared] + contract_ids + non_it_ids
    for i in range(0, len(ids), 500):
        q = db.query(Job).filter(Job.external_job_id.in_(ids[i:i + 500]))
        q = q.filter(Job.source == company_slug) if aggregator else q.filter(Job.company_id == company_id)
        for row in q.all():
            existing_by_id.setdefault(row.external_job_id, row)

    # Contract postings previously stored as jobs move out of /api/jobs.
    for ext in contract_ids:
        row = existing_by_id.get(ext)
        if row is not None and row.is_active:
            row.is_active = False
            row.employment_type = contract_type_by_ext.get(ext, "contract")

    # Non-IT postings saved before the IT-only policy stop showing.
    for ext in non_it_ids:
        row = existing_by_id.get(ext)
        if row is not None and row.is_active and row.user_id is None:
            row.is_active = False

    # 3. Update existing rows, collect new ones.
    employer_cache: dict = {}
    new_rows: list[dict] = []
    for scraped_job, external_id, fields in prepared:
        try:
            # An aggregator's job goes under its real employer. Rows already filed
            # under the feed are matched by feed + id, so they're moved, not duplicated.
            job_company_id = company_id
            employer = employer_name(company_slug, scraped_job)
            if employer:
                if employer not in employer_cache:
                    employer_cache[employer] = get_or_create_company(
                        db, employer_slug(employer), company_name=employer, resolver=resolver
                    ).id
                job_company_id = employer_cache[employer]

            existing = existing_by_id.get(external_id)
            if existing is not None:
                _refresh_existing(existing, fields, job_company_id, now)
                stats.updated += 1
            else:
                new_rows.append({
                    **fields,
                    "company_id": job_company_id,
                    "source": company_slug,
                    "external_job_id": external_id,
                    "is_active": True,
                    "status": "wishlist",
                    "date_found": now.date(),
                    "first_seen_at": now,
                    "last_seen_at": now,
                    "reposted_count": 0,
                    "effective_posted_at": effective_posted_at(fields["posted_date"], now),
                })
        except Exception as e:
            stats.errors += 1
            stats.first_error = stats.first_error or f"{type(e).__name__}: {e}"[:200]
            logger.error(f"Error saving job '{fields.get('title')}': {e}")

    # Reposts: same company + title closed within REPOST_WINDOW_DAYS, back under a new id.
    try:
        reposts = _find_reposts(db, {r["company_id"] for r in new_rows}, {r["title"] for r in new_rows}, now)
    except Exception as e:
        logger.info(f"Repost lookup failed for {company_slug}: {e}")
        reposts = {}
    for r in new_rows:
        prior = reposts.get((r["company_id"], normalize_title(r["title"])))
        if prior is not None:
            r["reposted_count"] = prior + 1
        ev, reason = evergreen_status(r["title"], r["job_description"],
                                      listed_days(r["effective_posted_at"], now), r["reposted_count"])
        r["is_evergreen"], r["evergreen_reason"] = ev, reason

    # 3b. Contract postings -> contract_jobs (same transaction as the updates).
    stats.contracts = _route_to_contracts(db, company_slug, company_id,
                                          "aggregator" if aggregator else "company_board",
                                          contract_jobs, detected)

    # 4. Commit the updates, then insert new rows chunk by chunk (each committed).
    try:
        db.commit()
    except Exception as e:
        logger.error(f"Failed to commit jobs for {company_slug}: {type(e).__name__}: {e}")
        _rollback(db)
        stats.commit_error = f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}"
        stats.new = stats.updated = stats.contracts = 0
        return stats

    try:
        _insert_jobs(db, new_rows, stats)
    except Exception as e:  # the connection is gone; updates above are already committed
        stats.errors += len(new_rows) - stats.new - stats.duplicates - stats.errors
        stats.first_error = stats.first_error or f"{type(e).__name__}: {e}"[:200]
        logger.error(f"Inserting jobs for {company_slug} failed: {e}")
        _rollback(db)

    log = logger.warning if (stats.saved == 0 and len(jobs) > 0 and not stats.contracts) else logger.info
    log(f"Saved jobs for {company_slug} ({len(jobs)} found): {stats.summary()}")
    return stats


_CONTENT_FIELDS = ("title", "company_id", "location", "job_url", "job_description", "department",
                   "posted_date", "salary_min", "salary_max", "is_active", "employment_type")


def _refresh_existing(existing: Job, fields: dict, company_id: int, now: datetime) -> None:
    """Refresh a re-seen row. last_seen_at always moves; updated_at only when content changed."""
    before = tuple(getattr(existing, f) for f in _CONTENT_FIELDS)
    old_posted = existing.posted_date
    new_posted = fields["posted_date"]
    if old_posted and new_posted and new_posted - old_posted >= timedelta(days=REPOST_REDATE_DAYS):
        existing.reposted_count = (existing.reposted_count or 0) + 1

    existing.title = fields["title"]
    existing.company_id = company_id
    existing.location = fields["location"] or existing.location
    existing.job_url = fields["job_url"]
    existing.job_description = fields["job_description"] or existing.job_description
    existing.department = fields["department"] or existing.department
    existing.posted_date = new_posted or old_posted
    existing.salary_min = fields["salary_min"] or existing.salary_min
    existing.salary_max = fields["salary_max"] or existing.salary_max
    existing.employment_type = fields.get("employment_type") or existing.employment_type
    if "country_codes" in fields:
        existing.country_codes = fields["country_codes"]
    existing.is_active = True  # Mark as still active
    existing.missed_runs = 0

    existing.first_seen_at = existing.first_seen_at or existing.created_at or now
    existing.last_seen_at = now
    # Earliest date we know of: a re-dated posting keeps its original listing date.
    existing.effective_posted_at = effective_posted_at(
        effective_posted_at(old_posted, existing.first_seen_at), new_posted)
    apply_freshness(existing, now)

    if tuple(getattr(existing, f) for f in _CONTENT_FIELDS) != before:
        existing.updated_at = now
    else:
        # Keep updated_at as is (the column has onupdate=now(), which would fire
        # for the last_seen_at-only UPDATE otherwise).
        flag_modified(existing, "updated_at")


# A posting missing from this many consecutive complete scrapes of its board is closed.
CLOSE_AFTER_MISSES = 2


def close_removed_postings(db: Session, company_slug: str, result) -> int:
    """
    After a complete, successful scrape of a company's board, count a miss for
    each active posting of that company + source the board no longer lists
    (jobs.missed_runs), clear it for those it lists, and close (is_active=False)
    those missed CLOSE_AFTER_MISSES runs in a row. Returns how many were closed.

    Never acts on a run that failed, found nothing, was cut short (page/job cap,
    time budget: result.complete is False) or whose save failed, and never for
    aggregator feeds or staffing agencies. The 14-day stale sweep still covers
    every other source.
    """
    stats = result.save_stats or {}
    if (
        not result.success
        or not getattr(result, "complete", False)
        or not result.jobs
        or stats.get("exception")
        or stats.get("commit_error")
        or company_slug in AGGREGATOR_SLUGS
    ):
        return 0
    metadata = ScraperRegistry.get_metadata(company_slug)
    if not metadata or metadata.get("category") == "staffing":
        return 0

    seen = {_clean_external_id(j.external_job_id or j.generate_id()) for j in result.jobs}
    try:
        company = get_or_create_company(db, company_slug, company_name=metadata["company_name"],
                                        website=metadata.get("careers_url"))
        rows = db.query(Job.id, Job.external_job_id, Job.missed_runs).filter(
            Job.company_id == company.id,
            Job.source == company_slug,
            Job.is_active == True,  # noqa: E712
            Job.user_id.is_(None),
        ).all()
        listed_again = [r.id for r in rows if r.external_job_id in seen and (r.missed_runs or 0) > 0]
        missing = [r for r in rows if r.external_job_id not in seen]
        to_close = [r.id for r in missing if (r.missed_runs or 0) + 1 >= CLOSE_AFTER_MISSES]
        to_count = [r.id for r in missing if (r.missed_runs or 0) + 1 < CLOSE_AFTER_MISSES]
        # Keep updated_at for bookkeeping-only changes (it is "content changed").
        for i in range(0, len(listed_again), 500):
            db.query(Job).filter(Job.id.in_(listed_again[i:i + 500])).update(
                {"missed_runs": 0, "updated_at": Job.updated_at}, synchronize_session=False)
        for i in range(0, len(to_count), 500):
            db.query(Job).filter(Job.id.in_(to_count[i:i + 500])).update(
                {"missed_runs": func.coalesce(Job.missed_runs, 0) + 1, "updated_at": Job.updated_at},
                synchronize_session=False)
        for i in range(0, len(to_close), 500):
            db.query(Job).filter(Job.id.in_(to_close[i:i + 500])).update(
                {"missed_runs": func.coalesce(Job.missed_runs, 0) + 1, "is_active": False},
                synchronize_session=False)
        db.commit()
    except Exception as e:
        logger.warning(f"Closing removed postings for {company_slug} failed: {type(e).__name__}: {e}")
        _rollback(db)
        return 0
    if to_close or to_count:
        logger.info(f"{company_slug}: closed {len(to_close)} postings no longer listed; "
                    f"{len(to_count)} missing for the first time")
    return len(to_close)


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
        "last_run_success": bool(recent_runs[0].success) if recent_runs else None,
        "last_run_jobs_found": recent_runs[0].jobs_found if recent_runs else None,
        "last_run_note": recent_runs[0].error_message if recent_runs else None,
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
        ScraperRun.jobs_found.label("jobs_found"),
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

    # The latest run itself: what it found, and its note (e.g. "saved: 0 new,
    # 0 updated, 21 skipped_old") so a 0-active board can say why.
    last_runs: dict[str, tuple] = {}
    for slug, success, jobs_found, message in db.query(
        ranked.c.slug, ranked.c.success, ranked.c.jobs_found, ranked.c.error_message
    ).filter(ranked.c.rn == 1).all():
        last_runs[slug] = (bool(success), jobs_found, message)

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
            "last_run_success": last_runs.get(slug, (None, None, None))[0],
            "last_run_jobs_found": last_runs.get(slug, (None, None, None))[1],
            "last_run_note": last_runs.get(slug, (None, None, None))[2],
            "active_jobs": active_jobs,
            "total_jobs": total_jobs,
        })
    return results
