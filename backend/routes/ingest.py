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
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime, date, timedelta
import logging
import json
import re
import urllib.request

from database import get_db
from models import Job, Company, IngestionSource, User
from services import ingestion_service
from utils.security import validate_url_ssrf_safe
from middleware.auth import get_current_user, get_current_admin, is_admin
from routes.settings import get_max_job_age_days
from services.company_resolver import CompanyResolver

# Admin-only (Depends(get_current_admin) per route), except
# POST /refetch-description/{job_id}, which the jobs site's job-detail page
# uses for jobs the user can see.
router = APIRouter(prefix="/api/ingest", tags=["ingestion"])
logger = logging.getLogger(__name__)


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


# ============== Helper Functions ==============


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
        # Normalized-name match so 'Snap Inc.' reuses the scraper's 'Snap' row.
        company = CompanyResolver(db).get_or_create(
            source.company_name, website=source.career_page_url
        )
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

            # Contract roles live in contract_jobs (contracts package)
            from services.scraper_service import route_contract_job_data
            if route_contract_job_data(db, source.ats_type, job_data, company.id, source_type="company_board"):
                if existing_job is not None and existing_job.is_active:
                    existing_job.is_active = False
                continue

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
                from services.job_freshness import touch_seen
                touch_seen(existing_job)
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
                from services.job_freshness import touch_seen
                touch_seen(new_job, is_new=True)
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

@router.post("/company", response_model=IngestCompanyResponse)
def ingest_company_jobs(
    request: IngestCompanyRequest,
    current_user: User = Depends(get_current_admin),
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


def refresh_all_sources(
    current_user: User = Depends(get_current_admin),
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


# The admin's Refresh button
@router.post("/refresh", response_model=RefreshResponse)
def refresh_sources_legacy(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Refresh every active ingestion source."""
    return refresh_all_sources(current_user=current_user, db=db)


@router.post("/refetch-description/{job_id}")
def refetch_single_job_description(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Re-fetch job description for a single job by ID (shared jobs and the
    user's own; admins any job).
    """
    query = db.query(Job).filter(Job.id == job_id)
    if not is_admin(current_user):
        query = query.filter(or_(Job.user_id == None, Job.user_id == current_user.id))  # noqa: E711
    job = query.first()

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


# Global progress tracking for description fetch
fetch_progress = {
    "status": "idle",
    "total": 0,
    "processed": 0,
    "updated": 0,
    "failed": 0,
    "started_at": None,
}


@router.get("/fetch-progress")
def get_fetch_progress(current_user: User = Depends(get_current_admin)):
    """Get current progress of description fetch operation."""
    return fetch_progress


@router.post("/fetch-all-descriptions")
def fetch_all_missing_descriptions(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """
    Fetch descriptions for ALL jobs with missing descriptions.
    Runs in background and processes all active jobs.
    """
    global fetch_progress
    from datetime import datetime

    # Get ALL jobs with missing descriptions (no limit)
    jobs_to_update = db.query(Job).filter(
        Job.is_active == True,
        Job.job_url.isnot(None),
        Job.job_url != '',
        or_(
            Job.job_description.is_(None),
            Job.job_description == '',
            Job.job_description == 'No description available.',
            func.length(Job.job_description) < 100
        )
    ).all()

    total_count = len(jobs_to_update)

    if total_count == 0:
        return {
            "message": "No jobs with missing descriptions found",
            "jobs_found": 0
        }

    job_ids = [j.id for j in jobs_to_update]

    # Initialize progress
    fetch_progress = {
        "status": "running",
        "total": total_count,
        "processed": 0,
        "updated": 0,
        "failed": 0,
        "started_at": datetime.utcnow().isoformat(),
    }

    def process_all_jobs():
        global fetch_progress
        import time
        from database import SessionLocal
        db_session = SessionLocal()

        try:
            for idx, job_id in enumerate(job_ids):
                job = db_session.query(Job).get(job_id)
                if not job or not job.job_url:
                    fetch_progress["failed"] += 1
                    fetch_progress["processed"] = idx + 1
                    continue

                try:
                    description = ''
                    job_url = job.job_url.lower()

                    # Eightfold - JS-rendered, needs Playwright
                    if 'eightfold.ai' in job_url:
                        try:
                            description = ingestion_service.fetch_eightfold_description_sync(job.job_url)
                        except Exception as e:
                            logger.warning(f"Playwright fetch failed for {job.job_url}: {e}")
                        if not description or len(description) < 100:
                            description = ingestion_service._fetch_eightfold_job_description(job.job_url)

                    # Greenhouse - Use API with ?content=true
                    elif 'greenhouse.io' in job_url:
                        try:
                            # Extract job ID from URL: /jobs/{id} or /job/{id}
                            import re
                            job_id_match = re.search(r'/jobs?/(\d+)', job.job_url)
                            if job_id_match:
                                job_id = job_id_match.group(1)
                                api_url = f"https://boards-api.greenhouse.io/v1/boards/*/jobs/{job_id}"
                                # Try to get company slug from URL
                                slug_match = re.search(r'greenhouse\.io/([^/]+)', job.job_url)
                                if slug_match:
                                    slug = slug_match.group(1)
                                    api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs/{job_id}"
                                    req = urllib.request.Request(api_url, headers={'User-Agent': 'JobTrails/1.0'})
                                    with urllib.request.urlopen(req, timeout=15, context=ingestion_service.ssl_context) as resp:
                                        data = json.loads(resp.read().decode('utf-8'))
                                        description = data.get('content', '')
                                        if description:
                                            description = ingestion_service.html_to_text(description)
                        except Exception as e:
                            logger.debug(f"Greenhouse API failed for {job.job_url}: {e}")
                            description = ingestion_service.fetch_job_description_from_url(job.job_url)

                    # Lever - Use API
                    elif 'lever.co' in job_url:
                        try:
                            import re
                            # Lever URLs: jobs.lever.co/{company}/{job_id}
                            match = re.search(r'lever\.co/([^/]+)/([a-f0-9-]+)', job.job_url)
                            if match:
                                company, job_id = match.groups()
                                api_url = f"https://api.lever.co/v0/postings/{company}/{job_id}"
                                req = urllib.request.Request(api_url, headers={'User-Agent': 'JobTrails/1.0'})
                                with urllib.request.urlopen(req, timeout=15, context=ingestion_service.ssl_context) as resp:
                                    data = json.loads(resp.read().decode('utf-8'))
                                    desc_html = data.get('descriptionHtml', '') or data.get('description', '')
                                    if desc_html:
                                        description = ingestion_service.html_to_text(desc_html)
                        except Exception as e:
                            logger.debug(f"Lever API failed for {job.job_url}: {e}")
                            description = ingestion_service.fetch_job_description_from_url(job.job_url)

                    # Ashby - Use API
                    elif 'ashbyhq.com' in job_url:
                        try:
                            import re
                            # Ashby URLs: jobs.ashbyhq.com/{company}/{job_id}
                            match = re.search(r'ashbyhq\.com/([^/]+)/([a-f0-9-]+)', job.job_url)
                            if match:
                                company, job_id = match.groups()
                                api_url = f"https://api.ashbyhq.com/posting-api/job-board/{company}/posting/{job_id}"
                                req = urllib.request.Request(api_url, headers={'User-Agent': 'JobTrails/1.0'})
                                with urllib.request.urlopen(req, timeout=15, context=ingestion_service.ssl_context) as resp:
                                    data = json.loads(resp.read().decode('utf-8'))
                                    description = data.get('descriptionHtml', '') or data.get('descriptionPlain', '')
                                    if description:
                                        description = ingestion_service.html_to_text(description)
                        except Exception as e:
                            logger.debug(f"Ashby API failed for {job.job_url}: {e}")
                            description = ingestion_service.fetch_job_description_from_url(job.job_url)

                    # SmartRecruiters
                    elif 'smartrecruiters.com' in job_url:
                        description = ingestion_service._fetch_smartrecruiters_job_description(job.job_url)

                    # GoHire
                    elif 'gohire.io' in job_url:
                        try:
                            job_data = ingestion_service._fetch_gohire_job_page(job.job_url)
                            if job_data:
                                description = job_data.get('job_description', '')
                        except Exception as e:
                            logger.debug(f"GoHire fetch failed: {e}")

                    # Generic fallback for other URLs
                    else:
                        description = ingestion_service.fetch_job_description_from_url(job.job_url)

                    if description and len(description) > 100:
                        job.job_description = description[:15000]
                        job.updated_at = datetime.utcnow()
                        db_session.commit()
                        fetch_progress["updated"] += 1
                    else:
                        fetch_progress["failed"] += 1

                    # Rate limiting (longer for Playwright)
                    time.sleep(0.5 if 'eightfold.ai' in job.job_url else 0.3)

                except Exception as e:
                    logger.error(f"Error fetching description for job {job_id}: {e}")
                    fetch_progress["failed"] += 1
                    db_session.rollback()

                fetch_progress["processed"] = idx + 1

        finally:
            db_session.close()
            fetch_progress["status"] = "completed"
            logger.info(f"Description fetch complete: {fetch_progress['updated']} updated, {fetch_progress['failed']} failed out of {len(job_ids)}")

    background_tasks.add_task(process_all_jobs)

    return {
        "message": f"Started fetching descriptions for {total_count} jobs in background",
        "jobs_queued": total_count,
        "mode": "background"
    }
