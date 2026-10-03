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

MAX_FAILURES = 5
# An opened job is fetched at most this often, however many people open it.
ON_DEMAND_COOLDOWN = timedelta(minutes=10)
# Pages that refuse a plain request: Meta answers 400 and lists its jobs only
# through its GraphQL search, so its descriptions need their own fetcher.
SKIP_SOURCES = ("meta",)

_VAGUE_LOCATION = re.compile(r"^\s*$|^\s*\d+\s+locations?\s*$|\(\+\d+ more\)", re.IGNORECASE)


def has_description(job) -> bool:
    return (job.job_description or "").strip() not in ("", "No description available.")


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


def fetch_description(db, job, on_demand: bool = False) -> tuple[str, int | None]:
    """
    Fetch and store ``job``'s description; commits. Returns (outcome, http status):
    'stored' (it already had one), 'fetched', 'closed' (Workday says the posting
    is gone; the job is retired), 'skipped' (no request made) or 'failed'.
    """
    if has_description(job):
        return "stored", None
    now = datetime.utcnow()
    if not job.job_url or job.source in SKIP_SOURCES:
        return "skipped", None
    if on_demand and job.description_fetch_attempted_at and now - job.description_fetch_attempted_at < ON_DEMAND_COOLDOWN:
        return "skipped", None
    job.description_fetch_attempted_at = now
    if not is_it_role(job.title, department=job.department):
        # Non-IT jobs are being retired (deactivate_non_it_jobs): no request.
        job.description_fetch_failures = MAX_FAILURES
        db.commit()
        return "skipped", None

    status = None
    if ingestion_service.workday_detail_api_url(job.job_url):
        # Workday: one JSON call gives the description and the full location list.
        status, info = ingestion_service.fetch_workday_posting(job.job_url)
        description = (info.get("jobDescription") or "").strip()
        fill_workday_location(job, info)
    else:
        description = ingestion_service.fetch_job_description_from_url(job.job_url)

    if description and len(description) > 100:
        job.job_description = description[:15000]
        job.description_fetch_failures = 0
        db.commit()
        return "fetched", status
    if status in (404, 410):
        job.is_active = False
        db.commit()
        return "closed", status
    job.description_fetch_failures = (job.description_fetch_failures or 0) + 1
    db.commit()
    return "failed", status
