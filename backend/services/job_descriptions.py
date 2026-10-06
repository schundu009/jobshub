"""
One job's description, fetched from its posting when the feed did not carry it.

Used by the 30-minute backfill (tasks.maintenance_tasks.fetch_missing_descriptions)
and on demand when someone opens a job that has none (POST
/api/jobs/{id}/description), so the posting can be read before applying.
No AI: the ATS's JSON (Workday) or the page's own text.
"""
import re
from datetime import datetime, timedelta

from services import ingestion_service
from services.it_roles import is_it_role
from services.salary import fill_salary

MAX_FAILURES = 5
# An opened job is fetched at most this often, however many people open it
# (Try again on the job page waits this out).
ON_DEMAND_COOLDOWN = timedelta(minutes=1)
# Sources whose pages give nothing to read (none at present: Meta's job pages
# carry a schema.org JobPosting, read by fetch_job_description_from_url).
SKIP_SOURCES: tuple = ()

_VAGUE_LOCATION = re.compile(r"^\s*$|^\s*\d+\s+locations?\s*$|\(\+\d+ more\)", re.IGNORECASE)


# Shorter than this is a list summary (Oracle sends 125 chars), not the posting.
THIN = 400


# A job whose fetch failed waits this long before the next try.
RETRY_HOURS = 12


def missing_filter():
    """SQL for an active job with a URL whose description is missing or thin
    (the same test as has_description), from a source that can be fetched."""
    from sqlalchemy import and_, func, or_
    from models import Job

    return and_(
        Job.is_active.is_(True),
        Job.job_url.isnot(None),
        Job.job_url != '',
        ~Job.source.in_(SKIP_SOURCES) if SKIP_SOURCES else True,
        or_(
            Job.job_description.is_(None),
            Job.job_description == 'No description available.',
            func.length(func.trim(Job.job_description)) < THIN,
            # SmartRecruiters stored with only its Company Description.
            and_(Job.job_url.like('%smartrecruiters.com/%'),
                 ~Job.job_description.ilike('%job description%'),
                 ~Job.job_description.ilike('%qualifications%')),
        ),
    )


def ready_filter(now: datetime):
    """Of the missing ones, those the backfill takes now: never tried, or
    failed more than RETRY_HOURS ago and fewer than MAX_FAILURES times."""
    from sqlalchemy import and_, func, or_
    from models import Job

    retry_cutoff = now - timedelta(hours=RETRY_HOURS)
    return and_(
        or_(Job.description_fetch_attempted_at.is_(None), Job.description_fetch_attempted_at < retry_cutoff),
        func.coalesce(Job.description_fetch_failures, 0) < MAX_FAILURES,
    )


def missing_counts(db, now: datetime | None = None) -> dict:
    """How many active jobs lack a description: ready to fetch, waiting to
    retry, and given up (MAX_FAILURES reached; the posting is likely gone)."""
    from sqlalchemy import func
    from models import Job

    now = now or datetime.utcnow()
    missing = db.query(Job.id).filter(missing_filter())
    total = missing.count()
    ready = missing.filter(ready_filter(now)).count()
    given_up = missing.filter(func.coalesce(Job.description_fetch_failures, 0) >= MAX_FAILURES).count()
    return {"missing": total, "ready": ready, "retrying_later": total - ready - given_up, "given_up": given_up}


def has_description(job) -> bool:
    text = (job.job_description or "").strip()
    if text == "No description available." or len(text) < THIN:
        return False
    # The SmartRecruiters page scrape kept only the Company Description: that
    # is the employer's blurb, not the job.
    if ingestion_service.smartrecruiters_detail_api_url(job.job_url) and not re.search(r"job description|qualifications", text, re.I):
        return False
    return True


def fill_workday_location(job, info: dict) -> None:
    """Replace a missing / "3 Locations" / "City (+2 more)" location with Workday's full list, and re-tag countries."""
    if not _VAGUE_LOCATION.search(job.location or ""):
        return
    location = ingestion_service.workday_posting_location(info)
    if not location:
        return
    from services.job_location import job_countries, to_country_codes
    job.location = location[:500]
    job.country_codes = to_country_codes(job_countries(job.location, job.title))


def fetch_posting(job_url: str) -> tuple:
    """
    Network only (safe to run in threads): (http status, description, workday
    info) for a posting URL. The ATS's own JSON where it has one (SmartRecruiters,
    Oracle, Workday), else the page (its schema.org JobPosting, then its text).
    """
    if ingestion_service.smartrecruiters_detail_api_url(job_url):
        status, description = ingestion_service.fetch_smartrecruiters_description(job_url)
        return status, description, {}
    if ingestion_service.oracle_detail_api_url(job_url):
        status, description = ingestion_service.fetch_oracle_description(job_url)
        return status, description, {}
    if ingestion_service.workday_detail_api_url(job_url):
        # One JSON call gives the description and the full location list.
        status, info = ingestion_service.fetch_workday_posting(job_url)
        return status, (info.get("jobDescription") or "").strip(), info
    return None, ingestion_service.fetch_job_description_from_url(job_url), {}


def claim(db, job, on_demand: bool = False):
    """
    Decide whether ``job`` needs a request: the outcome to report when it does
    not ('stored' or 'skipped'), else None (and the attempt is stamped).
    """
    if has_description(job):
        return "stored"
    now = datetime.utcnow()
    if not job.job_url or job.source in SKIP_SOURCES:
        return "skipped"
    if on_demand and job.description_fetch_attempted_at and now - job.description_fetch_attempted_at < ON_DEMAND_COOLDOWN:
        return "skipped"
    job.description_fetch_attempted_at = now
    if not is_it_role(job.title, department=job.department):
        # Non-IT jobs are being retired (deactivate_non_it_jobs): no request.
        job.description_fetch_failures = MAX_FAILURES
        return "skipped"
    return None


def store(db, job, status, description: str, info: dict) -> str:
    """Record a fetch's result on ``job``; commits. 'fetched', 'closed' or 'failed'."""
    if info:
        fill_workday_location(job, info)
    if description and len(description) > max(100, len((job.job_description or "").strip())):
        job.job_description = description[:15000]
        job.description_fetch_failures = 0
        fill_salary(job)
        db.commit()
        return "fetched"
    if status in (404, 410):
        job.is_active = False
        db.commit()
        return "closed"
    job.description_fetch_failures = (job.description_fetch_failures or 0) + 1
    db.commit()
    return "failed"


def fetch_description(db, job, on_demand: bool = False) -> tuple[str, int | None]:
    """
    Fetch and store ``job``'s description; commits. Returns (outcome, http status):
    'stored' (it already had one), 'fetched', 'closed' (Workday says the posting
    is gone; the job is retired), 'skipped' (no request made) or 'failed'.
    """
    skip = claim(db, job, on_demand)
    if skip:
        db.commit()
        return skip, None
    status, description, info = fetch_posting(job.job_url)
    return store(db, job, status, description, info), status


def fetch_many(db, jobs, workers: int = 8, per_host: int = 2) -> dict:
    """
    The backfill's batch: claim in this thread, fetch in a pool (at most
    ``per_host`` requests to one site at a time), store in this thread.
    Returns outcome counts and the failures for the run's report.
    """
    import threading
    from collections import defaultdict
    from concurrent.futures import ThreadPoolExecutor
    from urllib.parse import urlparse

    counts: dict = defaultdict(int)
    failed: list = []
    todo = []
    for job in jobs:
        skip = claim(db, job)
        if skip:
            counts[skip] += 1
        else:
            todo.append(job)
    db.commit()

    gates: dict = defaultdict(lambda: threading.Semaphore(per_host))
    lock = threading.Lock()

    def one(url):
        host = urlparse(url).netloc.lower()
        with lock:
            gate = gates[host]
        with gate:
            try:
                return fetch_posting(url)
            except Exception as e:  # one bad page never stops the batch
                return None, "", {"_error": str(e)[:200]}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(one, [j.job_url for j in todo]))
    for job, (status, description, info) in zip(todo, results):
        error = info.pop("_error", None) if info else None
        try:
            outcome = store(db, job, status, description, info)
        except Exception as e:
            db.rollback()
            outcome, error = "failed", str(e)[:200]
        counts[outcome] += 1
        if outcome == "failed":
            failed.append({"id": job.id, "title": job.title, "url": job.job_url,
                           "reason": error or (f"HTTP {status}" if status else "Empty or short description returned")})
    return {"counts": dict(counts), "failed": failed}
