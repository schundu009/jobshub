"""
Job ingestion routes for importing jobs from ATS platforms.
Includes bulk source management and auto-discovery.

Security features:
- JWT authentication required for all endpoints
- SSRF protection on URL validation
- Input length limits
- Content type validation
- User-scoped data access (multi-tenancy)
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime, date, timedelta
import csv
import json
import io
import re
import signal
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError

from database import get_db
from models import Job, Company, IngestionSource, User, AppSetting
from services import ingestion_service
from utils.security import validate_url_ssrf_safe
from middleware.auth import get_current_user
from routes.settings import get_max_job_age_days

router = APIRouter(prefix="/api/ingest", tags=["ingestion"])


def extract_salary(description: str) -> tuple:
    """
    Extract salary range from job description.
    Returns (min_salary, max_salary) or (None, None) if not found.
    """
    if not description:
        return None, None

    # Normalize dashes and clean up
    text = description.replace('—', '-').replace('–', '-')
    text = re.sub(r'<[^>]+>', ' ', text)  # Remove HTML tags
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace

    # Salary patterns (order matters - more specific first)
    patterns = [
        # $320,000.00-$405,000.00 USD or $128,880.00-245,160.00 USD (with decimals)
        r'\$\s*([\d,]+)(?:\.\d{2})?\s*-\s*\$?\s*([\d,]+)(?:\.\d{2})?\s*(?:USD)?',
        # $150K - $200K or $150k-$200k
        r'\$\s*(\d+)\s*[kK]\s*-\s*\$?\s*(\d+)\s*[kK]',
        # $150,000 to $200,000
        r'\$\s*([\d,]+)(?:\.\d{2})?\s+to\s+\$?\s*([\d,]+)(?:\.\d{2})?',
        # Salary/compensation: $150,000 - $200,000
        r'(?:salary|compensation|pay|base|range|annual)[:\s]+\$?\s*([\d,]+)(?:\.\d{2})?\s*-\s*\$?\s*([\d,]+)(?:\.\d{2})?',
        # USD 150,000 - 200,000
        r'USD\s*([\d,]+)(?:\.\d{2})?\s*-\s*([\d,]+)(?:\.\d{2})?',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            min_str = match.group(1).replace(',', '')
            max_str = match.group(2).replace(',', '') if match.lastindex >= 2 else None

            # Handle K notation
            if len(min_str) <= 3 and int(min_str) < 1000:
                min_val = int(min_str) * 1000
            else:
                min_val = int(min_str)

            max_val = None
            if max_str:
                if len(max_str) <= 3 and int(max_str) < 1000:
                    max_val = int(max_str) * 1000
                else:
                    max_val = int(max_str)

            # Validate reasonable salary range (30k - 2M for tech)
            if 30000 <= min_val <= 2000000:
                if max_val and max_val >= min_val and max_val <= 2000000:
                    return min_val, max_val
                elif max_val and max_val < min_val:
                    # Swap if reversed
                    return max_val, min_val
                elif not max_val:
                    return min_val, None

    return None, None


def parse_posted_date(date_str):
    """Parse posted date string to datetime object."""
    if not date_str:
        return None
    if isinstance(date_str, datetime):
        return date_str
    try:
        # Try ISO format with timezone
        if 'T' in date_str:
            # Remove timezone info for SQLite compatibility
            # Handle both +HH:MM and -HH:MM timezone formats
            if '+' in date_str:
                date_str = date_str.split('+')[0]
            elif date_str.count('-') > 2:
                # Timezone offset like -05:00, split at the last hyphen before colon
                parts = date_str.rsplit('-', 1)
                if ':' in parts[-1]:
                    date_str = parts[0]
            if date_str.endswith('Z'):
                date_str = date_str[:-1]
            return datetime.fromisoformat(date_str)
        # Try date only
        return datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError) as e:
        print(f"Error parsing date {date_str}: {e}")
        return None


# ============== Pydantic Models ==============

class IngestCompanyRequest(BaseModel):
    """Request to ingest jobs from a company career page."""
    career_page_url: str = Field(..., min_length=10, max_length=500)
    company_name: Optional[str] = Field(None, max_length=255)

    @field_validator('career_page_url')
    @classmethod
    def validate_url(cls, v):
        is_valid, error = validate_url_ssrf_safe(v)
        if not is_valid:
            raise ValueError(error)
        return v


class AddCustomCompanyRequest(BaseModel):
    """Request to add a company with a custom career page (no auto-import)."""
    career_page_url: str = Field(..., min_length=10, max_length=500)
    company_name: str = Field(..., min_length=1, max_length=255)

    @field_validator('career_page_url')
    @classmethod
    def validate_url(cls, v):
        is_valid, error = validate_url_ssrf_safe(v)
        if not is_valid:
            raise ValueError(error)
        return v


class AddCustomCompanyResponse(BaseModel):
    """Response after adding a custom company."""
    company_id: int
    company_name: str
    career_page_url: str
    message: str


class IngestCompanyResponse(BaseModel):
    """Response after ingesting jobs."""
    company_name: str
    ats_type: str
    jobs_added: int
    jobs_updated: int
    jobs_deactivated: int
    total_active_jobs: int


class RefreshResponse(BaseModel):
    """Response after refreshing all sources."""
    sources_refreshed: int
    sources_failed: int
    total_jobs_added: int
    total_jobs_updated: int
    total_jobs_deactivated: int


class BatchRefreshResponse(BaseModel):
    """Response after batch refresh."""
    batch_number: int
    batch_size: int
    sources_in_batch: int
    sources_refreshed: int
    sources_failed: int
    jobs_added: int
    jobs_updated: int
    jobs_deactivated: int
    total_active_sources: int
    has_more: bool
    next_offset: int


class SourceUploadResponse(BaseModel):
    """Response after uploading sources."""
    sources_added: int
    sources_skipped: int
    errors: List[str]


class BulkSourceRequest(BaseModel):
    """Request to add multiple sources."""
    sources: List[dict]


class IngestionSourceInfo(BaseModel):
    """Information about an ingestion source."""
    id: int
    company_name: Optional[str]
    ats_type: str
    ats_company_slug: str
    career_page_url: Optional[str]
    created_at: Optional[datetime]
    last_checked_at: Optional[datetime]
    last_successful_at: Optional[datetime]
    job_count: int
    is_active: bool
    error_message: Optional[str]


# ============== Helper Functions ==============

# Per-source timeout (seconds) - prevents one slow source from blocking everything
SOURCE_TIMEOUT_SECONDS = 120

# Slow companies - these have slow APIs (mainly Workday) and should be processed separately
SLOW_COMPANIES = [
    'nvidia', 'spacex', 'salesforce', 'comcast', 'amazon', 'dell', 'intel',
    'broadcom', 'workday', 'walmart', 'target', 'cisco', 'hp', 'ibm', 'oracle'
]


def is_slow_company(company_name: str) -> bool:
    """Check if a company is considered slow (substring match)."""
    if not company_name:
        return False
    name_lower = company_name.lower()
    return any(slow in name_lower for slow in SLOW_COMPANIES)


def ingest_from_source_with_timeout(source: IngestionSource, db: Session, timeout: int = SOURCE_TIMEOUT_SECONDS) -> dict:
    """
    Wrapper that runs ingest_from_source with a timeout.
    Uses ThreadPoolExecutor for timeout handling.
    """
    result = {
        "success": False,
        "jobs_added": 0,
        "jobs_updated": 0,
        "jobs_deactivated": 0,
        "jobs_skipped_old": 0,
        "error": None
    }

    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(ingest_from_source, source, db)
            try:
                result = future.result(timeout=timeout)
            except FuturesTimeoutError:
                result["error"] = f"Timeout after {timeout}s"
                # Update source with timeout error
                source.last_checked_at = datetime.utcnow()
                source.error_message = f"Timeout after {timeout}s"
                db.commit()
    except Exception as e:
        result["error"] = str(e)

    return result


def ingest_from_source(source: IngestionSource, db: Session, _is_retry: bool = False) -> dict:
    """
    Ingest jobs from a single source.
    Only ingests jobs posted within the configured max job age (default 30 days).
    Returns dict with results.
    """
    result = {
        "success": False,
        "jobs_added": 0,
        "jobs_updated": 0,
        "jobs_deactivated": 0,
        "jobs_skipped_old": 0,
        "error": None
    }

    # Get configurable max job age from settings
    max_job_age_days = get_max_job_age_days(db)
    cutoff_date = datetime.utcnow() - timedelta(days=max_job_age_days)

    # Update last_checked_at
    source.last_checked_at = datetime.utcnow()

    try:
        jobs_data = ingestion_service.fetch_jobs_from_ats(source.ats_type, source.ats_company_slug)
    except ValueError as e:
        source.error_message = str(e)[:500]
        source.job_count = 0
        db.commit()
        result["error"] = str(e)
        return result

    if not jobs_data:
        source.error_message = "No jobs found"
        source.job_count = 0
        db.commit()
        result["error"] = "No jobs found"
        return result

    # Clear any previous error
    source.error_message = None
    source.last_successful_at = datetime.utcnow()

    # Get or create company name
    if not source.company_name:
        source.company_name = ingestion_service.get_company_name_from_slug(source.ats_company_slug)

    # Get or create the Company record
    company = None
    if source.company_id:
        company = db.query(Company).filter(Company.id == source.company_id).first()

    if not company:
        company = db.query(Company).filter(Company.name == source.company_name).first()
        if not company:
            company = Company(
                name=source.company_name,
                website=source.career_page_url
            )
            db.add(company)
            db.commit()
            db.refresh(company)
        source.company_id = company.id

    # Track external IDs we've seen (only for recent jobs)
    fetched_external_ids = set()
    recent_jobs_count = 0

    try:
        for job_data in jobs_data:
            external_id = job_data['external_job_id']
            posted_date = parse_posted_date(job_data.get('posted_date'))

            # Skip jobs older than max_job_age_days (configurable in settings)
            if posted_date and posted_date < cutoff_date:
                result["jobs_skipped_old"] += 1
                continue

            fetched_external_ids.add(external_id)
            recent_jobs_count += 1

            existing_job = db.query(Job).filter(
                Job.source == source.ats_type,
                Job.external_job_id == external_id
            ).first()

            # Extract salary from description
            salary_min, salary_max = extract_salary(job_data['job_description'])

            if existing_job:
                existing_job.title = job_data['title']
                existing_job.location = job_data['location']
                existing_job.job_url = job_data['job_url']
                existing_job.job_description = job_data['job_description']
                existing_job.is_active = True
                existing_job.posted_date = posted_date
                existing_job.department = job_data.get('department')
                if salary_min:
                    existing_job.salary_min = salary_min
                if salary_max:
                    existing_job.salary_max = salary_max
                result["jobs_updated"] += 1
            else:
                new_job = Job(
                    title=job_data['title'],
                    company_id=company.id,
                    location=job_data['location'],
                    job_url=job_data['job_url'],
                    job_description=job_data['job_description'],
                    source=source.ats_type,
                    external_job_id=external_id,
                    status='wishlist',
                    date_found=date.today(),
                    excitement_level=3,
                    is_active=True,
                    posted_date=posted_date,
                    department=job_data.get('department'),
                    salary_min=salary_min,
                    salary_max=salary_max
                )
                db.add(new_job)
                result["jobs_added"] += 1

        # Update job count to only reflect recent jobs
        source.job_count = recent_jobs_count

        # Mark removed jobs as inactive
        if fetched_external_ids:
            jobs_to_deactivate = db.query(Job).filter(
                Job.source == source.ats_type,
                Job.company_id == company.id,
                Job.is_active == True,
                ~Job.external_job_id.in_(fetched_external_ids)
            ).all()

            for job in jobs_to_deactivate:
                job.is_active = False
                result["jobs_deactivated"] += 1

        # Also deactivate jobs older than max_job_age_days from this company
        old_jobs = db.query(Job).filter(
            Job.company_id == company.id,
            Job.is_active == True,
            Job.posted_date < cutoff_date
        ).all()

        for job in old_jobs:
            job.is_active = False
            result["jobs_deactivated"] += 1

        db.commit()
        result["success"] = True

    except Exception as e:
        db.rollback()
        error_msg = str(e)

        # Check for sequence/primary key errors and try to fix (only once)
        if not _is_retry and ("duplicate key" in error_msg.lower() or "unique" in error_msg.lower()):
            try:
                # Fix sequence
                from sqlalchemy import text
                max_id_result = db.execute(text("SELECT MAX(id) FROM jobs"))
                max_id = max_id_result.scalar() or 0
                db.execute(text("SELECT setval('jobs_id_seq', :val, true)"), {"val": max_id})
                db.commit()

                # Retry the ingestion with fixed sequence
                return ingest_from_source(source, db, _is_retry=True)
            except Exception as fix_error:
                result["error"] = f"Database error (sequence fix failed): {error_msg[:200]}"
        else:
            result["error"] = f"Database error: {error_msg[:300]}"

        return result

    return result


# ============== Endpoints ==============

@router.post("/sources/upload", response_model=SourceUploadResponse)
async def upload_sources(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a CSV or JSON file with company sources to track.

    CSV format (with header):
    ats_type,company_slug,company_name
    greenhouse,stripe,Stripe
    greenhouse,anthropic,Anthropic
    lever,netflix,Netflix

    JSON format:
    [
        {"ats_type": "greenhouse", "company_slug": "stripe", "company_name": "Stripe"},
        {"ats_type": "greenhouse", "company_slug": "anthropic", "company_name": "Anthropic"}
    ]

    company_name is optional - will be auto-generated from slug if not provided.
    """
    content = await file.read()
    content_str = content.decode('utf-8')

    sources_to_add = []
    errors = []

    # Determine file type
    filename = file.filename.lower() if file.filename else ""

    if filename.endswith('.json') or content_str.strip().startswith('['):
        # Parse as JSON
        try:
            data = json.loads(content_str)
            if not isinstance(data, list):
                raise ValueError("JSON must be an array of objects")
            sources_to_add = data
        except json.JSONDecodeError as e:
            raise HTTPException(status_code=400, detail=f"Invalid JSON: {str(e)}")
    else:
        # Parse as CSV
        try:
            reader = csv.DictReader(io.StringIO(content_str))
            for row in reader:
                sources_to_add.append({
                    "ats_type": row.get('ats_type', '').strip().lower(),
                    "company_slug": row.get('company_slug', '').strip(),
                    "company_name": row.get('company_name', '').strip() or None
                })
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid CSV: {str(e)}")

    added = 0
    skipped = 0

    for source_data in sources_to_add:
        ats_type = source_data.get('ats_type', '').lower()
        company_slug = source_data.get('company_slug', '')
        company_name = source_data.get('company_name')

        # Validate
        if not ats_type or not company_slug:
            errors.append(f"Missing ats_type or company_slug: {source_data}")
            continue

        if ats_type not in ['greenhouse', 'lever', 'ashby', 'smartrecruiters', 'workable', 'recruitee', 'workday', 'apple']:
            errors.append(f"Invalid ats_type '{ats_type}' for {company_slug}")
            continue

        # Check for duplicate
        existing = db.query(IngestionSource).filter(
            IngestionSource.ats_type == ats_type,
            IngestionSource.ats_company_slug == company_slug
        ).first()

        if existing:
            skipped += 1
            continue

        # Generate company_name if not provided
        if not company_name:
            company_name = ingestion_service.get_company_name_from_slug(company_slug)

        # Create new source
        new_source = IngestionSource(
            ats_type=ats_type,
            ats_company_slug=company_slug,
            company_name=company_name,
            is_active=True,
            job_count=0
        )
        db.add(new_source)
        added += 1

    db.commit()

    return SourceUploadResponse(
        sources_added=added,
        sources_skipped=skipped,
        errors=errors
    )


@router.post("/sources/bulk", response_model=SourceUploadResponse)
def add_sources_bulk(
    request: BulkSourceRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add multiple sources via JSON body.

    Example:
    {
        "sources": [
            {"ats_type": "greenhouse", "company_slug": "stripe"},
            {"ats_type": "greenhouse", "company_slug": "anthropic", "company_name": "Anthropic"}
        ]
    }
    """
    added = 0
    skipped = 0
    errors = []

    for source_data in request.sources:
        ats_type = source_data.get('ats_type', '').lower()
        company_slug = source_data.get('company_slug', '')
        company_name = source_data.get('company_name')

        if not ats_type or not company_slug:
            errors.append(f"Missing ats_type or company_slug: {source_data}")
            continue

        if ats_type not in ['greenhouse', 'lever', 'ashby', 'smartrecruiters', 'workable', 'recruitee', 'workday', 'apple']:
            errors.append(f"Invalid ats_type '{ats_type}' for {company_slug}")
            continue

        existing = db.query(IngestionSource).filter(
            IngestionSource.ats_type == ats_type,
            IngestionSource.ats_company_slug == company_slug
        ).first()

        if existing:
            skipped += 1
            continue

        if not company_name:
            company_name = ingestion_service.get_company_name_from_slug(company_slug)

        new_source = IngestionSource(
            ats_type=ats_type,
            ats_company_slug=company_slug,
            company_name=company_name,
            is_active=True,
            job_count=0
        )
        db.add(new_source)
        added += 1

    db.commit()

    return SourceUploadResponse(
        sources_added=added,
        sources_skipped=skipped,
        errors=errors
    )


@router.post("/sources/refresh", response_model=RefreshResponse)
def refresh_all_sources(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Refresh jobs from ALL active ingestion sources.
    This is the auto-ingestion loop.

    For each active source:
    1. Fetch jobs from ATS
    2. Add/update jobs in database
    3. Mark removed jobs as inactive
    4. Update last_checked_at timestamp
    5. Mark source inactive if company not found
    """
    sources = db.query(IngestionSource).filter(IngestionSource.is_active == True).all()

    if not sources:
        return RefreshResponse(
            sources_refreshed=0,
            sources_failed=0,
            total_jobs_added=0,
            total_jobs_updated=0,
            total_jobs_deactivated=0
        )

    total_added = 0
    total_updated = 0
    total_deactivated = 0
    sources_refreshed = 0
    sources_failed = 0

    for source in sources:
        result = ingest_from_source(source, db)

        if result["success"]:
            sources_refreshed += 1
            total_added += result["jobs_added"]
            total_updated += result["jobs_updated"]
            total_deactivated += result["jobs_deactivated"]
        else:
            sources_failed += 1

    return RefreshResponse(
        sources_refreshed=sources_refreshed,
        sources_failed=sources_failed,
        total_jobs_added=total_added,
        total_jobs_updated=total_updated,
        total_jobs_deactivated=total_deactivated
    )


@router.post("/sources/{source_id}/refresh")
def refresh_single_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Refresh jobs from a single ingestion source.
    """
    source = db.query(IngestionSource).filter(IngestionSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")

    result = ingest_from_source(source, db)

    return {
        "source_id": source_id,
        "company_name": source.company_name,
        "success": result["success"],
        "jobs_added": result["jobs_added"],
        "jobs_updated": result["jobs_updated"],
        "jobs_deactivated": result["jobs_deactivated"],
        "error": result["error"]
    }


@router.post("/sources/refresh/batch", response_model=BatchRefreshResponse)
def refresh_sources_batch(
    batch_size: int = 10,
    offset: int = 0,
    timeout_per_source: int = 120,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Refresh jobs from active ingestion sources in batches with per-source timeouts.

    Use this for incremental ingestion to avoid timeouts.

    Args:
        batch_size: Number of sources to process (default 10, max 50)
        offset: Starting offset (default 0)
        timeout_per_source: Max seconds per source (default 120, max 300)

    Example workflow:
        1. Call with offset=0, batch_size=10 to process first 10 sources
        2. If has_more=true, call again with offset=next_offset
        3. Repeat until has_more=false
    """
    # Cap batch size and timeout to prevent overload
    batch_size = min(batch_size, 50)
    timeout_per_source = min(timeout_per_source, 300)

    # Get total count of active sources
    total_active = db.query(IngestionSource).filter(IngestionSource.is_active == True).count()

    if total_active == 0:
        return BatchRefreshResponse(
            batch_number=0,
            batch_size=batch_size,
            sources_in_batch=0,
            sources_refreshed=0,
            sources_failed=0,
            jobs_added=0,
            jobs_updated=0,
            jobs_deactivated=0,
            total_active_sources=0,
            has_more=False,
            next_offset=0
        )

    # Get batch of sources ordered by ID for consistent pagination
    sources = db.query(IngestionSource).filter(
        IngestionSource.is_active == True
    ).order_by(IngestionSource.id).offset(offset).limit(batch_size).all()

    if not sources:
        return BatchRefreshResponse(
            batch_number=offset // batch_size,
            batch_size=batch_size,
            sources_in_batch=0,
            sources_refreshed=0,
            sources_failed=0,
            jobs_added=0,
            jobs_updated=0,
            jobs_deactivated=0,
            total_active_sources=total_active,
            has_more=False,
            next_offset=offset
        )

    jobs_added = 0
    jobs_updated = 0
    jobs_deactivated = 0
    sources_refreshed = 0
    sources_failed = 0

    for source in sources:
        # Use timeout wrapper to prevent one slow source from blocking
        result = ingest_from_source_with_timeout(source, db, timeout=timeout_per_source)

        if result["success"]:
            sources_refreshed += 1
            jobs_added += result["jobs_added"]
            jobs_updated += result["jobs_updated"]
            jobs_deactivated += result["jobs_deactivated"]
        else:
            sources_failed += 1

    next_offset = offset + len(sources)
    has_more = next_offset < total_active

    return BatchRefreshResponse(
        batch_number=offset // batch_size,
        batch_size=batch_size,
        sources_in_batch=len(sources),
        sources_refreshed=sources_refreshed,
        sources_failed=sources_failed,
        jobs_added=jobs_added,
        jobs_updated=jobs_updated,
        jobs_deactivated=jobs_deactivated,
        total_active_sources=total_active,
        has_more=has_more,
        next_offset=next_offset
    )


# Store for background batch job status and logs
_batch_job_status = {}
_batch_job_logs = {}  # job_id -> list of log entries
MAX_LOGS_PER_JOB = 500  # Limit logs to prevent memory issues


def add_batch_log(job_id: str, level: str, message: str, source: str = None):
    """Add a log entry to a batch job."""
    if job_id not in _batch_job_logs:
        _batch_job_logs[job_id] = []

    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "level": level,  # info, success, error, warning
        "message": message,
        "source": source
    }
    _batch_job_logs[job_id].append(log_entry)

    # Trim old logs if exceeding limit
    if len(_batch_job_logs[job_id]) > MAX_LOGS_PER_JOB:
        _batch_job_logs[job_id] = _batch_job_logs[job_id][-MAX_LOGS_PER_JOB:]


@router.post("/sources/refresh/batch/async")
def start_batch_refresh_async(
    batch_size: int = 10,
    timeout_per_source: int = 120,
    exclude_slow: bool = False,
    slow_only: bool = False,
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Start a background batch refresh of active sources.

    This endpoint returns immediately with a job_id.
    Use GET /sources/refresh/batch/status/{job_id} to check progress.

    Args:
        batch_size: Number of sources to process per batch (default 10, max 50)
        timeout_per_source: Max seconds per source (default 120, max 300)
        exclude_slow: If true, exclude slow companies (Nvidia, Workday ATS, etc.)
        slow_only: If true, only process slow companies
    """
    import uuid
    from database import SessionLocal

    job_id = str(uuid.uuid4())[:8]
    batch_size = min(batch_size, 50)
    timeout_per_source = min(timeout_per_source, 300)

    # Build query for sources, filtering by slow company preference
    query = db.query(IngestionSource).filter(IngestionSource.is_active == True)

    # Get all active sources
    all_sources = query.all()

    # Filter based on slow company settings
    if exclude_slow:
        filtered_sources = [
            s for s in all_sources
            if not is_slow_company(s.company_name) and s.ats_type != 'workday'
        ]
    elif slow_only:
        filtered_sources = [
            s for s in all_sources
            if is_slow_company(s.company_name) or s.ats_type == 'workday'
        ]
    else:
        filtered_sources = all_sources

    total_active = len(filtered_sources)
    source_ids = [s.id for s in filtered_sources]

    # Initialize status and logs
    mode = "slow companies only" if slow_only else ("excluding slow companies" if exclude_slow else "all sources")
    _batch_job_status[job_id] = {
        "status": "running",
        "started_at": datetime.utcnow().isoformat(),
        "total_sources": total_active,
        "processed": 0,
        "sources_refreshed": 0,
        "sources_failed": 0,
        "jobs_added": 0,
        "jobs_updated": 0,
        "jobs_deactivated": 0,
        "current_source": None,
        "error": None,
        "mode": mode
    }
    _batch_job_logs[job_id] = []
    add_batch_log(job_id, "info", f"Batch job started ({mode}). Processing {total_active} sources with batch_size={batch_size}")

    def run_batch_job(job_source_ids: list):
        """Background task to process specified sources in batches."""
        offset = 0
        batch_num = 0

        while True:
            # Check if job was stopped
            if _batch_job_status.get(job_id, {}).get("status") == "stopped":
                add_batch_log(job_id, "warning", "Batch job stopped by user")
                break

            # Get batch of sources by ID
            batch_ids = job_source_ids[offset:offset + batch_size]
            if not batch_ids:
                break

            batch_num += 1
            add_batch_log(job_id, "info", f"Starting batch {batch_num} ({len(batch_ids)} sources)")

            for source_id in batch_ids:
                # Check if job was stopped
                if _batch_job_status.get(job_id, {}).get("status") == "stopped":
                    add_batch_log(job_id, "warning", "Batch job stopped by user")
                    break

                # Create fresh session for each source to avoid session state issues
                db_session = SessionLocal()
                try:
                    source = db_session.query(IngestionSource).filter(
                        IngestionSource.id == source_id
                    ).first()

                    if not source:
                        _batch_job_status[job_id]["processed"] += 1
                        _batch_job_status[job_id]["sources_failed"] += 1
                        add_batch_log(job_id, "error", f"✗ Source ID {source_id} not found")
                        continue

                    _batch_job_status[job_id]["current_source"] = source.company_name
                    add_batch_log(job_id, "info", f"Processing: {source.company_name} ({source.ats_type})", source.company_name)

                    result = ingest_from_source_with_timeout(source, db_session, timeout=timeout_per_source)

                    _batch_job_status[job_id]["processed"] += 1

                    if result["success"]:
                        _batch_job_status[job_id]["sources_refreshed"] += 1
                        _batch_job_status[job_id]["jobs_added"] += result["jobs_added"]
                        _batch_job_status[job_id]["jobs_updated"] += result["jobs_updated"]
                        _batch_job_status[job_id]["jobs_deactivated"] += result["jobs_deactivated"]

                        jobs_info = f"+{result['jobs_added']} added, ~{result['jobs_updated']} updated"
                        add_batch_log(job_id, "success", f"✓ {source.company_name}: {jobs_info}", source.company_name)
                    else:
                        _batch_job_status[job_id]["sources_failed"] += 1
                        error_msg = result.get("error", "Unknown error")
                        add_batch_log(job_id, "error", f"✗ {source.company_name}: {error_msg}", source.company_name)

                except Exception as e:
                    _batch_job_status[job_id]["processed"] += 1
                    _batch_job_status[job_id]["sources_failed"] += 1
                    add_batch_log(job_id, "error", f"✗ Source ID {source_id}: {str(e)}")
                    db_session.rollback()
                finally:
                    db_session.close()

            offset += batch_size

        # Only mark as completed if not stopped
        if _batch_job_status.get(job_id, {}).get("status") != "stopped":
            _batch_job_status[job_id]["status"] = "completed"
            _batch_job_status[job_id]["completed_at"] = datetime.utcnow().isoformat()
            _batch_job_status[job_id]["current_source"] = None

            stats = _batch_job_status[job_id]
            add_batch_log(job_id, "success", f"Batch completed! {stats['sources_refreshed']} refreshed, {stats['sources_failed']} failed. Jobs: +{stats['jobs_added']} added, ~{stats['jobs_updated']} updated")
        else:
            _batch_job_status[job_id]["completed_at"] = datetime.utcnow().isoformat()
            _batch_job_status[job_id]["current_source"] = None

    # Start background task with the list of source IDs
    if background_tasks:
        background_tasks.add_task(run_batch_job, source_ids)
    else:
        # Fallback to thread if BackgroundTasks not available
        thread = threading.Thread(target=run_batch_job, args=(source_ids,), daemon=True)
        thread.start()

    return {
        "job_id": job_id,
        "status": "started",
        "total_sources": total_active,
        "mode": mode,
        "message": f"Background batch refresh started ({mode}). Check status at /api/ingest/sources/refresh/batch/status/{job_id}"
    }


@router.get("/sources/refresh/batch/status/{job_id}")
def get_batch_refresh_status(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get the status of a background batch refresh job.
    """
    if job_id not in _batch_job_status:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    return _batch_job_status[job_id]


@router.post("/sources/refresh/batch/stop/{job_id}")
def stop_batch_refresh(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Stop a running batch refresh job.
    The job will stop after completing the current source.
    """
    if job_id not in _batch_job_status:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    status = _batch_job_status[job_id]
    if status["status"] != "running":
        raise HTTPException(status_code=400, detail=f"Job {job_id} is not running (status: {status['status']})")

    _batch_job_status[job_id]["status"] = "stopped"
    add_batch_log(job_id, "warning", "Stop requested - will stop after current source completes")

    return {
        "job_id": job_id,
        "status": "stopping",
        "message": "Job will stop after the current source completes"
    }


@router.get("/sources/refresh/batch/jobs")
def list_batch_jobs(current_user: User = Depends(get_current_user)):
    """
    List all batch refresh jobs and their status.
    """
    return {
        "jobs": [
            {"job_id": job_id, **status}
            for job_id, status in _batch_job_status.items()
        ]
    }


@router.get("/sources/refresh/batch/logs/{job_id}")
def get_batch_logs(
    job_id: str,
    since: int = 0,
    current_user: User = Depends(get_current_user)
):
    """
    Get logs for a batch job.

    Args:
        job_id: The batch job ID
        since: Return logs after this index (for polling new logs)
    """
    if job_id not in _batch_job_status:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    logs = _batch_job_logs.get(job_id, [])
    return {
        "job_id": job_id,
        "total_logs": len(logs),
        "logs": logs[since:],  # Return logs after 'since' index
        "next_since": len(logs)
    }


@router.get("/sources/refresh/batch/stream/{job_id}")
async def stream_batch_logs(
    job_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Stream batch job logs using Server-Sent Events (SSE).
    Connect to this endpoint to receive real-time log updates.
    """
    from fastapi.responses import StreamingResponse
    import asyncio

    if job_id not in _batch_job_status:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

    async def event_generator():
        last_index = 0
        while True:
            # Get current status and new logs
            status = _batch_job_status.get(job_id, {})
            logs = _batch_job_logs.get(job_id, [])

            # Send new logs
            new_logs = logs[last_index:]
            for log in new_logs:
                yield f"data: {json.dumps({'type': 'log', 'data': log})}\n\n"
            last_index = len(logs)

            # Send status update
            yield f"data: {json.dumps({'type': 'status', 'data': status})}\n\n"

            # If job is completed or failed, send final message and stop
            if status.get("status") in ["completed", "failed"]:
                yield f"data: {json.dumps({'type': 'done', 'data': status})}\n\n"
                break

            await asyncio.sleep(1)  # Poll every second

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.post("/company/custom", response_model=AddCustomCompanyResponse)
def add_custom_company(
    request: AddCustomCompanyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Add a company with a custom career page URL (no auto-import).
    Use this for companies that don't use supported ATS platforms.
    You can manually add jobs for this company later.
    """
    # Check if ingestion source already exists for this URL
    existing_source = db.query(IngestionSource).filter(
        IngestionSource.career_page_url == request.career_page_url
    ).first()

    if existing_source:
        return AddCustomCompanyResponse(
            company_id=existing_source.company_id,
            company_name=existing_source.company_name,
            career_page_url=request.career_page_url,
            message=f"Company '{existing_source.company_name}' already tracked. You can add jobs manually."
        )

    # Check if company already exists by name
    existing_company = db.query(Company).filter(
        Company.name.ilike(request.company_name)
    ).first()

    if existing_company:
        # Update the website if not set
        if not existing_company.website:
            existing_company.website = request.career_page_url
            db.commit()
        company = existing_company
    else:
        # Create new company
        company = Company(
            name=request.company_name,
            website=request.career_page_url
        )
        db.add(company)
        db.commit()
        db.refresh(company)

    # Create ingestion source for tracking (marked as 'custom' type)
    new_source = IngestionSource(
        ats_type="custom",
        ats_company_slug=request.company_name.lower().replace(" ", "-"),
        company_name=request.company_name,
        career_page_url=request.career_page_url,
        company_id=company.id,
        is_active=True
    )
    db.add(new_source)
    db.commit()

    return AddCustomCompanyResponse(
        company_id=company.id,
        company_name=company.name,
        career_page_url=request.career_page_url,
        message=f"Company '{company.name}' added. You can now add jobs manually for this company."
    )


@router.post("/company", response_model=IngestCompanyResponse)
def ingest_company_jobs(
    request: IngestCompanyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Ingest jobs from a company's career page URL.
    Auto-detects the ATS type and creates/updates the ingestion source.
    """
    ats_type, company_slug = ingestion_service.detect_ats_type(request.career_page_url)

    if not ats_type:
        raise HTTPException(
            status_code=400,
            detail="Could not detect ATS type from URL. Supported: Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, Workday, Apple, Intuit, ADP. For other sites, use 'Add Custom Company' to track manually."
        )

    # Get or create the ingestion source
    source = db.query(IngestionSource).filter(
        IngestionSource.ats_type == ats_type,
        IngestionSource.ats_company_slug == company_slug
    ).first()

    if not source:
        company_name = ingestion_service.get_company_name_from_slug(company_slug)
        source = IngestionSource(
            ats_type=ats_type,
            ats_company_slug=company_slug,
            company_name=company_name,
            career_page_url=request.career_page_url,
            is_active=True,
            job_count=0
        )
        db.add(source)
        db.commit()
        db.refresh(source)
    else:
        # Update career page URL if provided
        source.career_page_url = request.career_page_url
        source.is_active = True

    # Ingest jobs
    result = ingest_from_source(source, db)

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    total_active = db.query(Job).filter(
        Job.company_id == source.company_id,
        Job.is_active == True
    ).count()

    return IngestCompanyResponse(
        company_name=source.company_name,
        ats_type=ats_type,
        jobs_added=result["jobs_added"],
        jobs_updated=result["jobs_updated"],
        jobs_deactivated=result["jobs_deactivated"],
        total_active_jobs=total_active
    )


# Keep the old /refresh endpoint for backwards compatibility
@router.post("/refresh", response_model=RefreshResponse)
def refresh_sources_legacy(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Legacy endpoint - redirects to /sources/refresh
    """
    return refresh_all_sources(current_user=current_user, db=db)


@router.get("/sources")
def list_ingestion_sources(
    active_only: bool = False,
    ats_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all ingestion sources with optional filtering.
    """
    query = db.query(IngestionSource)

    if active_only:
        query = query.filter(IngestionSource.is_active == True)

    if ats_type:
        query = query.filter(IngestionSource.ats_type == ats_type)

    sources = query.order_by(IngestionSource.company_name).all()

    result = []
    for source in sources:
        result.append({
            "id": source.id,
            "company_name": source.company_name,
            "ats_type": source.ats_type,
            "ats_company_slug": source.ats_company_slug,
            "career_page_url": source.career_page_url,
            "created_at": source.created_at,
            "last_checked_at": source.last_checked_at,
            "last_successful_at": source.last_successful_at,
            "job_count": source.job_count or 0,
            "is_active": source.is_active,
            "error_message": source.error_message
        })

    return result


@router.get("/sources/stats")
def get_sources_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get statistics about ingestion sources.
    """
    total = db.query(IngestionSource).count()
    active = db.query(IngestionSource).filter(IngestionSource.is_active == True).count()
    with_errors = db.query(IngestionSource).filter(IngestionSource.error_message != None).count()

    by_ats = {}
    for ats in ['greenhouse', 'lever', 'ashby', 'workday', 'smartrecruiters', 'workable', 'recruitee', 'apple', 'intuit', 'adp', 'custom']:
        count = db.query(IngestionSource).filter(IngestionSource.ats_type == ats).count()
        if count > 0:
            by_ats[ats] = count

    total_jobs = db.query(Job).filter(Job.source != 'manual').count()

    return {
        "total_sources": total,
        "active_sources": active,
        "sources_with_errors": with_errors,
        "by_ats_type": by_ats,
        "total_jobs_imported": total_jobs
    }


@router.put("/sources/{source_id}")
def update_ingestion_source(
    source_id: int,
    company_name: Optional[str] = None,
    ats_type: Optional[str] = None,
    ats_company_slug: Optional[str] = None,
    career_page_url: Optional[str] = None,
    is_active: Optional[bool] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an ingestion source configuration.
    Useful for fixing ATS configurations (e.g., CrowdStrike Workday slug).
    """
    source = db.query(IngestionSource).filter(IngestionSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail=f"Source {source_id} not found")

    if company_name is not None:
        source.company_name = company_name
    if ats_type is not None:
        source.ats_type = ats_type
    if ats_company_slug is not None:
        source.ats_company_slug = ats_company_slug
        # Clear error message when slug is updated
        source.error_message = None
    if career_page_url is not None:
        source.career_page_url = career_page_url
    if is_active is not None:
        source.is_active = is_active

    db.commit()
    db.refresh(source)

    return {
        "id": source.id,
        "company_name": source.company_name,
        "ats_type": source.ats_type,
        "ats_company_slug": source.ats_company_slug,
        "career_page_url": source.career_page_url,
        "is_active": source.is_active,
        "message": "Source updated successfully"
    }


@router.delete("/sources/{source_id}")
def delete_ingestion_source(
    source_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete an ingestion source.
    Jobs already imported will remain in the database.
    """
    source = db.query(IngestionSource).filter(IngestionSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Ingestion source not found")

    db.delete(source)
    db.commit()
    return {"message": "Ingestion source deleted successfully"}


@router.patch("/sources/{source_id}")
def update_ingestion_source(
    source_id: int,
    is_active: Optional[bool] = None,
    company_name: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update an ingestion source (activate/deactivate, rename).
    """
    source = db.query(IngestionSource).filter(IngestionSource.id == source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Ingestion source not found")

    if is_active is not None:
        source.is_active = is_active
    if company_name is not None:
        source.company_name = company_name

    db.commit()

    return {
        "id": source.id,
        "company_name": source.company_name,
        "is_active": source.is_active
    }


@router.get("/detect")
def detect_ats_from_url(
    url: str,
    current_user: User = Depends(get_current_user)
):
    """
    Detect the ATS type from a career page URL without ingesting.
    """
    ats_type, company_slug = ingestion_service.detect_ats_type(url)

    if not ats_type:
        return {
            "detected": False,
            "message": "Could not detect ATS type. Supported: Greenhouse, Lever, Ashby, SmartRecruiters, Workable, Recruitee, Workday, Apple"
        }

    return {
        "detected": True,
        "ats_type": ats_type,
        "company_slug": company_slug,
        "company_name": ingestion_service.get_company_name_from_slug(company_slug)
    }


@router.get("/supported-platforms")
def get_supported_platforms(current_user: User = Depends(get_current_user)):
    """
    Get information about all supported ATS platforms.
    """
    return ingestion_service.get_supported_ats_info()


@router.post("/cleanup-old-jobs")
def cleanup_old_jobs(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Delete jobs older than specified days from the database.
    Default is 30 days.
    """
    cutoff_date = datetime.utcnow() - timedelta(days=days)

    # Count jobs to delete
    old_jobs_query = db.query(Job).filter(
        Job.posted_date < cutoff_date
    )
    old_jobs_with_null = db.query(Job).filter(
        Job.posted_date == None,
        Job.created_at < cutoff_date
    )

    count_with_date = old_jobs_query.count()
    count_with_null = old_jobs_with_null.count()

    # Delete old jobs
    old_jobs_query.delete(synchronize_session=False)
    old_jobs_with_null.delete(synchronize_session=False)

    db.commit()

    return {
        "deleted_jobs": count_with_date + count_with_null,
        "deleted_with_old_posted_date": count_with_date,
        "deleted_with_null_posted_date": count_with_null,
        "cutoff_date": cutoff_date.isoformat()
    }


@router.post("/fix-sequences")
def fix_database_sequences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Fix PostgreSQL sequences that are out of sync with table data.
    This can happen after bulk imports or database restores.
    """
    from sqlalchemy import text

    tables_fixed = []

    # List of tables with auto-increment IDs to fix
    tables = [
        ("jobs", "id"),
        ("companies", "id"),
        ("ingestion_sources", "id"),
        ("contacts", "id"),
        ("interviews", "id"),
        ("notes", "id"),
        ("documents", "id"),
        ("users", "id"),
        ("role_profiles", "id"),
        ("user_documents", "id"),
        ("job_relevance_scores", "id"),
        ("scraper_runs", "id"),
        ("scraper_configs", "id"),
    ]

    for table, column in tables:
        try:
            # Get the sequence name (PostgreSQL naming convention)
            seq_name = f"{table}_{column}_seq"

            # Get max ID from table
            result = db.execute(text(f"SELECT MAX({column}) FROM {table}"))
            max_id = result.scalar() or 0

            # Reset sequence to max_id + 1
            db.execute(text(f"SELECT setval('{seq_name}', :val, true)"), {"val": max_id})

            tables_fixed.append({
                "table": table,
                "sequence": seq_name,
                "max_id": max_id,
                "new_nextval": max_id + 1
            })
        except Exception as e:
            tables_fixed.append({
                "table": table,
                "error": str(e)[:200]
            })

    db.commit()

    return {
        "message": "Sequences fixed",
        "tables": tables_fixed
    }


@router.post("/refetch-descriptions")
async def refetch_missing_descriptions(
    background_tasks: BackgroundTasks,
    company_name: Optional[str] = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Re-fetch job descriptions for jobs that are missing them.
    Can filter by company name. Runs in background for large batches.
    """
    import time

    # Query for jobs with missing or empty descriptions
    query = db.query(Job).filter(
        (Job.job_description == None) |
        (Job.job_description == '') |
        (Job.job_description.like('No description%'))
    )

    if company_name:
        # Get company by name
        company = db.query(Company).filter(
            Company.name.ilike(f"%{company_name}%")
        ).first()
        if company:
            query = query.filter(Job.company_id == company.id)

    jobs_to_update = query.limit(limit).all()

    if not jobs_to_update:
        return {
            "message": "No jobs found with missing descriptions",
            "jobs_found": 0
        }

    # For small batches, process immediately
    if len(jobs_to_update) <= 10:
        updated_count = 0
        failed_count = 0

        for job in jobs_to_update:
            if not job.job_url:
                failed_count += 1
                continue

            try:
                description = ingestion_service.fetch_job_description_from_url(job.job_url)
                if description and len(description) > 100:
                    job.job_description = description
                    updated_count += 1
                else:
                    failed_count += 1
                time.sleep(0.3)  # Rate limiting
            except Exception:
                failed_count += 1

        db.commit()

        return {
            "message": f"Processed {len(jobs_to_update)} jobs",
            "updated": updated_count,
            "failed": failed_count,
            "mode": "immediate"
        }
    else:
        # For larger batches, process in background
        job_ids = [j.id for j in jobs_to_update]

        def process_batch():
            from database import SessionLocal
            db_session = SessionLocal()
            try:
                updated = 0
                for job_id in job_ids:
                    job = db_session.query(Job).get(job_id)
                    if job and job.job_url:
                        try:
                            description = ingestion_service.fetch_job_description_from_url(job.job_url)
                            if description and len(description) > 100:
                                job.job_description = description
                                updated += 1
                                db_session.commit()
                            time.sleep(0.3)
                        except Exception:
                            pass
            finally:
                db_session.close()

        background_tasks.add_task(process_batch)

        return {
            "message": f"Started background processing for {len(jobs_to_update)} jobs",
            "jobs_queued": len(jobs_to_update),
            "mode": "background"
        }


@router.post("/refetch-description/{job_id}")
async def refetch_single_job_description(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Re-fetch job description for a single job by ID.
    """
    job = db.query(Job).filter(Job.id == job_id).first()

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if not job.job_url:
        raise HTTPException(status_code=400, detail="Job has no URL to fetch from")

    try:
        description = ingestion_service.fetch_job_description_from_url(job.job_url)

        if description and len(description) > 100:
            old_len = len(job.job_description) if job.job_description else 0
            job.job_description = description
            db.commit()

            return {
                "message": "Job description updated",
                "job_id": job_id,
                "title": job.title,
                "old_description_length": old_len,
                "new_description_length": len(description)
            }
        else:
            return {
                "message": "Could not extract description from job URL",
                "job_id": job_id,
                "job_url": job.job_url
            }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching description: {str(e)}")


@router.post("/fetch-all-descriptions")
async def fetch_all_missing_descriptions(
    background_tasks: BackgroundTasks,
    batch_size: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Fetch descriptions for ALL jobs with missing descriptions.
    Runs in background and processes all active jobs from last 30 days.
    """
    from datetime import datetime, timedelta

    cutoff = datetime.utcnow() - timedelta(days=30)

    # Count jobs with missing descriptions
    jobs_to_update = db.query(Job).filter(
        Job.is_active == True,
        Job.job_url.isnot(None),
        Job.job_url != '',
        Job.created_at >= cutoff,
        or_(
            Job.job_description.is_(None),
            Job.job_description == '',
            Job.job_description == 'No description available.',
            func.length(Job.job_description) < 100
        )
    ).limit(batch_size).all()

    total_count = len(jobs_to_update)

    if total_count == 0:
        return {
            "message": "No jobs with missing descriptions found",
            "jobs_found": 0
        }

    job_ids = [j.id for j in jobs_to_update]

    def process_all_jobs():
        import time
        from database import SessionLocal
        db_session = SessionLocal()
        updated = 0
        failed = 0

        try:
            for idx, job_id in enumerate(job_ids):
                job = db_session.query(Job).get(job_id)
                if not job or not job.job_url:
                    failed += 1
                    continue

                try:
                    # Try generic fetch first
                    description = ingestion_service.fetch_job_description_from_url(job.job_url)

                    # If that fails, try ATS-specific methods
                    if not description or len(description) < 100:
                        if 'eightfold.ai' in job.job_url:
                            description = ingestion_service._fetch_eightfold_job_description(job.job_url)
                        elif 'smartrecruiters.com' in job.job_url:
                            description = ingestion_service._fetch_smartrecruiters_job_description(job.job_url)

                    if description and len(description) > 100:
                        job.job_description = description[:15000]
                        job.updated_at = datetime.utcnow()
                        db_session.commit()
                        updated += 1
                    else:
                        failed += 1

                    # Rate limiting
                    time.sleep(0.5)

                except Exception as e:
                    logger.error(f"Error fetching description for job {job_id}: {e}")
                    failed += 1
                    db_session.rollback()

        finally:
            db_session.close()
            logger.info(f"Description fetch complete: {updated} updated, {failed} failed out of {len(job_ids)}")

    background_tasks.add_task(process_all_jobs)

    return {
        "message": f"Started fetching descriptions for {total_count} jobs in background",
        "jobs_queued": total_count,
        "mode": "background"
    }
