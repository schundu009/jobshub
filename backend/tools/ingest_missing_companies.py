#!/usr/bin/env python3
"""
Ingest jobs from all missing companies.
Targets only the 37 companies that were missing from the database.

Usage:
    cd /Users/chundu/jobportal/backend
    python tools/ingest_missing_companies.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from models import IngestionSource, Job, Company
from services import ingestion_service
from datetime import datetime, date, timedelta
import re

# The 37 companies that were missing from the database
MISSING_COMPANIES = [
    "Airbnb", "Asana", "Atlassian", "Brex", "Canva", "Cloudflare", "Coinbase",
    "Datadog", "DoorDash", "Dropbox", "Elastic", "GitHub", "Google", "Grammarly",
    "HashiCorp", "HubSpot", "Instacart", "Lyft", "Microsoft", "MongoDB", "Netflix",
    "Okta", "Palantir", "Pinterest", "Reddit", "Rippling", "Robinhood", "ServiceNow",
    "Shopify", "Snap", "Block (Square)", "Twilio", "X (Twitter)", "Uber", "Unity",
    "VMware", "Waymo"
]


def extract_salary(description: str) -> tuple:
    """Extract salary range from job description."""
    if not description:
        return None, None

    text = description.replace('—', '-').replace('–', '-')
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text)

    patterns = [
        r'\$\s*([\d,]+)(?:\.\d{2})?\s*-\s*\$?\s*([\d,]+)(?:\.\d{2})?\s*(?:USD)?',
        r'\$\s*(\d+)\s*[kK]\s*-\s*\$?\s*(\d+)\s*[kK]',
        r'\$\s*([\d,]+)(?:\.\d{2})?\s+to\s+\$?\s*([\d,]+)(?:\.\d{2})?',
    ]

    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            min_str = match.group(1).replace(',', '')
            max_str = match.group(2).replace(',', '') if match.lastindex >= 2 else None

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

            if 30000 <= min_val <= 2000000:
                if max_val and max_val >= min_val and max_val <= 2000000:
                    return min_val, max_val
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
        if 'T' in date_str:
            if '+' in date_str:
                date_str = date_str.split('+')[0]
            elif date_str.count('-') > 2:
                parts = date_str.rsplit('-', 1)
                if ':' in parts[-1]:
                    date_str = parts[0]
            if date_str.endswith('Z'):
                date_str = date_str[:-1]
            return datetime.fromisoformat(date_str)
        return datetime.strptime(date_str, '%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def ingest_source(source, db):
    """Ingest jobs from a single source."""
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    source.last_checked_at = datetime.utcnow()

    result = {
        "success": False,
        "jobs_added": 0,
        "jobs_updated": 0,
        "error": None
    }

    try:
        jobs_data = ingestion_service.fetch_jobs_from_ats(source.ats_type, source.ats_company_slug)
    except ValueError as e:
        source.error_message = str(e)[:500]
        db.commit()
        result["error"] = str(e)
        return result

    if not jobs_data:
        source.error_message = "No jobs found"
        db.commit()
        result["error"] = "No jobs found"
        return result

    source.error_message = None
    source.last_successful_at = datetime.utcnow()

    if not source.company_name:
        source.company_name = ingestion_service.get_company_name_from_slug(source.ats_company_slug)

    # Get or create Company
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

    recent_jobs_count = 0

    for job_data in jobs_data:
        external_id = job_data['external_job_id']
        posted_date = parse_posted_date(job_data.get('posted_date'))

        if posted_date and posted_date < cutoff_date:
            continue

        recent_jobs_count += 1

        existing_job = db.query(Job).filter(
            Job.source == source.ats_type,
            Job.external_job_id == external_id
        ).first()

        salary_min, salary_max = extract_salary(job_data.get('job_description', ''))

        if existing_job:
            existing_job.title = job_data['title']
            existing_job.location = job_data['location']
            existing_job.job_url = job_data['job_url']
            existing_job.job_description = job_data.get('job_description', '')
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
                job_description=job_data.get('job_description', ''),
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

    source.job_count = recent_jobs_count
    db.commit()
    result["success"] = True
    return result


def main():
    """Ingest jobs from all missing companies."""
    db = SessionLocal()

    print("=" * 60)
    print("Ingesting jobs from missing companies...")
    print("=" * 60)

    total_added = 0
    total_updated = 0
    success_count = 0
    fail_count = 0

    # Find sources matching our missing companies
    sources = db.query(IngestionSource).filter(
        IngestionSource.is_active == True
    ).all()

    # Filter to only missing companies
    missing_lower = [c.lower() for c in MISSING_COMPANIES]
    target_sources = []
    for source in sources:
        company_name = source.company_name.lower() if source.company_name else ""
        if any(m in company_name or company_name in m for m in missing_lower):
            target_sources.append(source)

    print(f"\nFound {len(target_sources)} matching sources to ingest\n")

    for i, source in enumerate(target_sources, 1):
        print(f"[{i}/{len(target_sources)}] {source.company_name} ({source.ats_type})...", end=" ", flush=True)

        result = ingest_source(source, db)

        if result["success"]:
            success_count += 1
            total_added += result["jobs_added"]
            total_updated += result["jobs_updated"]
            print(f"✓ Added: {result['jobs_added']}, Updated: {result['jobs_updated']}")
        else:
            fail_count += 1
            print(f"✗ Error: {result['error'][:50] if result['error'] else 'Unknown'}")

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Companies processed: {len(target_sources)}")
    print(f"Successful: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Total jobs added: {total_added}")
    print(f"Total jobs updated: {total_updated}")

    db.close()


if __name__ == "__main__":
    main()
