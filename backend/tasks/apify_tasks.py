"""
Apify Scheduled Tasks.

Periodic tasks to scrape jobs from job boards using Apify.
These complement the company-specific scrapers by providing
broad coverage from LinkedIn, Indeed, and Glassdoor.
"""

import logging
from datetime import datetime, timedelta

from celery import shared_task

from database import SessionLocal
from services.apify_service import get_apify_service, APIFY_ACTORS
from services.scraper_service import MAX_JOB_AGE_DAYS

logger = logging.getLogger(__name__)


def save_apify_jobs_to_db(jobs: list[dict], source: str) -> tuple[int, int]:
    """
    Save jobs from Apify to database.

    Args:
        jobs: List of parsed jobs from Apify
        source: Source identifier (linkedin, indeed, glassdoor)

    Returns:
        Tuple of (jobs_saved, companies_created)
    """
    from models import Job, Company
    from services.company_resolver import CompanyResolver

    jobs_saved = 0
    companies_created = 0
    jobs_skipped_old = 0
    companies_cache = {}
    resolver = None
    cutoff_date = datetime.utcnow() - timedelta(days=MAX_JOB_AGE_DAYS)

    with SessionLocal() as db:
        for job_data in jobs:
            try:
                # Skip jobs older than MAX_JOB_AGE_DAYS
                posted_date = job_data.get("posted_date")
                if posted_date:
                    if isinstance(posted_date, str):
                        try:
                            from dateutil import parser
                            posted_date = parser.parse(posted_date)
                        except Exception:
                            posted_date = None
                    if isinstance(posted_date, datetime):
                        posted_naive = posted_date.replace(tzinfo=None) if posted_date.tzinfo else posted_date
                        if posted_naive < cutoff_date:
                            jobs_skipped_old += 1
                            continue

                # Get company name
                raw_data = job_data.get("raw_data", {}) or {}
                company_name = raw_data.get("company_name") or job_data.get("company_name", "Unknown")

                if company_name not in companies_cache:
                    # Normalized-name match ('Snap Inc.' == 'Snap'); one resolver per batch
                    if resolver is None:
                        resolver = CompanyResolver(db)
                    before = resolver.find(company_name)
                    company = before or resolver.get_or_create(
                        company_name,
                        website=job_data.get("job_url", "").split("/job")[0] if job_data.get("job_url") else None,
                    )
                    if before is None:
                        companies_created += 1

                    companies_cache[company_name] = company

                company = companies_cache[company_name]

                # Contract roles live in contract_jobs (contracts package)
                from services.scraper_service import route_contract_job_data
                if route_contract_job_data(db, source, job_data, company.id, source_type="aggregator"):
                    continue

                # Check if job already exists
                external_job_id = job_data.get("external_job_id", "")
                if external_job_id:
                    existing = db.query(Job).filter(
                        Job.company_id == company.id,
                        Job.external_job_id == external_job_id
                    ).first()

                    if existing:
                        # Update existing job
                        existing.title = job_data.get("title", existing.title)
                        existing.job_description = job_data.get("job_description") or job_data.get("description") or existing.job_description
                        existing.location = job_data.get("location") or existing.location
                        existing.updated_at = datetime.utcnow()
                        from services.job_freshness import touch_seen
                        touch_seen(existing)
                        continue

                # Create new job
                job = Job(
                    title=job_data.get("title", ""),
                    company_id=company.id,
                    location=job_data.get("location", ""),
                    job_url=job_data.get("job_url", ""),
                    external_job_id=external_job_id,
                    job_description=job_data.get("job_description") or job_data.get("description", ""),
                    department=job_data.get("department", ""),
                    salary_min=job_data.get("salary_min"),
                    salary_max=job_data.get("salary_max"),
                    source=source,
                    is_active=True,
                    status="wishlist",
                )

                # Parse posted date
                posted_date = job_data.get("posted_date")
                if posted_date:
                    if isinstance(posted_date, str):
                        try:
                            from dateutil import parser
                            job.posted_date = parser.parse(posted_date)
                        except:
                            pass
                    elif isinstance(posted_date, datetime):
                        job.posted_date = posted_date

                from services.job_freshness import touch_seen
                touch_seen(job, is_new=True)
                db.add(job)
                jobs_saved += 1

            except Exception as e:
                logger.error(f"Failed to save job: {e}", exc_info=True)
                continue

        try:
            db.commit()
            logger.info(f"Apify {source}: Saved {jobs_saved} jobs, {companies_created} companies")
        except Exception as e:
            logger.error(f"Failed to commit Apify jobs: {e}", exc_info=True)
            db.rollback()
            return 0, 0

    return jobs_saved, companies_created


@shared_task(name="tasks.apify_tasks.scrape_apify_indeed")
def scrape_apify_indeed(search_queries: list[str] = None, max_items: int = 100):
    """
    Scrape jobs from Indeed using Apify.

    Args:
        search_queries: List of search queries (default: common tech roles)
        max_items: Max jobs per query
    """
    import asyncio

    if search_queries is None:
        # Role-based searches
        role_queries = [
            "software engineer",
            "backend engineer",
            "frontend developer",
            "data engineer",
            "devops engineer",
            "product manager",
            "machine learning engineer",
        ]

        # Fortune 500 + Top Tech Companies (comprehensive list)
        fortune_500_companies = [
            # Big Tech (FAANG+)
            "Google", "Microsoft", "Amazon", "Apple", "Meta", "Netflix", "Nvidia",
            # Tech Giants
            "Salesforce", "Adobe", "Oracle", "IBM", "Intel", "Cisco", "SAP",
            "VMware", "ServiceNow", "Workday", "Snowflake", "Databricks",
            # Social/Consumer Tech
            "LinkedIn", "Twitter", "Snap", "Pinterest", "Reddit", "Discord",
            # Ride-sharing/Delivery
            "Uber", "Lyft", "DoorDash", "Instacart",
            # Travel/Hospitality
            "Airbnb", "Booking", "Expedia", "Tripadvisor",
            # Fintech
            "Stripe", "Square", "PayPal", "Visa", "Mastercard", "American Express",
            "Goldman Sachs", "JPMorgan", "Morgan Stanley", "Citadel", "Jane Street",
            "Capital One", "Robinhood", "Coinbase", "Plaid",
            # E-commerce/Retail
            "Walmart", "Target", "Costco", "Home Depot", "Best Buy", "Wayfair", "Shopify",
            # Healthcare/Pharma
            "UnitedHealth", "CVS", "Johnson & Johnson", "Pfizer", "Merck", "Abbott",
            # Automotive/Mobility
            "Tesla", "GM", "Ford", "Rivian", "Lucid", "Waymo", "Cruise",
            # Aerospace/Defense
            "SpaceX", "Boeing", "Lockheed Martin", "Raytheon", "Northrop Grumman",
            # AI/ML Companies
            "OpenAI", "Anthropic", "DeepMind", "Cohere", "Hugging Face", "Scale AI",
            # Data/Analytics
            "Palantir", "Splunk", "Tableau", "Alteryx", "Datadog", "New Relic",
            # Cloud/Infrastructure
            "Cloudflare", "Akamai", "Fastly", "DigitalOcean", "MongoDB", "Elastic",
            # Security
            "CrowdStrike", "Palo Alto Networks", "Fortinet", "Okta", "Zscaler",
            # Enterprise Software
            "Atlassian", "Zoom", "Slack", "Dropbox", "Box", "DocuSign", "Twilio",
            # Gaming
            "Electronic Arts", "Activision", "Roblox", "Unity", "Epic Games",
            # Media/Entertainment
            "Disney", "Warner Bros", "Comcast", "Paramount", "Sony",
            # Telecom
            "Verizon", "AT&T", "T-Mobile",
            # Consulting/Services
            "Accenture", "Deloitte", "McKinsey", "BCG", "Bain",
            # Energy
            "ExxonMobil", "Chevron", "ConocoPhillips",
        ]

        company_queries = [f"{company} software engineer" for company in fortune_500_companies]
        search_queries = role_queries + company_queries

    service = get_apify_service()

    if not service.is_configured:
        logger.warning("Apify not configured, skipping Indeed scrape")
        return {"status": "skipped", "reason": "Apify not configured"}

    total_saved = 0
    total_companies = 0

    for query in search_queries:
        try:
            logger.info(f"Apify Indeed: Searching for '{query}'")

            # Run actor
            result = asyncio.get_event_loop().run_until_complete(
                service.run_actor(
                    actor_key="indeed_jobs",
                    input_override={
                        "searchQueries": [query],
                        "location": "United States",
                        "maxItems": max_items,
                    },
                    wait_for_finish=True,
                    timeout_secs=300,
                )
            )

            if result.get("status") == "success":
                jobs = result.get("jobs", [])
                saved, created = save_apify_jobs_to_db(jobs, "indeed")
                total_saved += saved
                total_companies += created
                logger.info(f"Apify Indeed '{query}': {len(jobs)} found, {saved} saved")
            else:
                logger.warning(f"Apify Indeed '{query}' failed: {result.get('error')}")

        except Exception as e:
            logger.exception(f"Error scraping Indeed for '{query}': {e}")

    return {
        "status": "completed",
        "queries": len(search_queries),
        "jobs_saved": total_saved,
        "companies_created": total_companies,
    }


@shared_task(name="tasks.apify_tasks.scrape_apify_linkedin")
def scrape_apify_linkedin(search_queries: list[str] = None, max_items: int = 50):
    """
    Scrape jobs from LinkedIn using Apify.

    Note: LinkedIn actors may require paid subscription.

    Args:
        search_queries: List of search queries
        max_items: Max jobs per query
    """
    import asyncio

    if search_queries is None:
        search_queries = [
            "software engineer",
            "data scientist",
            "product manager",
        ]

    service = get_apify_service()

    if not service.is_configured:
        logger.warning("Apify not configured, skipping LinkedIn scrape")
        return {"status": "skipped", "reason": "Apify not configured"}

    total_saved = 0
    total_companies = 0

    for query in search_queries:
        try:
            logger.info(f"Apify LinkedIn: Searching for '{query}'")

            result = asyncio.get_event_loop().run_until_complete(
                service.run_actor(
                    actor_key="linkedin_jobs",
                    input_override={
                        "searchQueries": [query],
                        "location": "United States",
                        "maxItems": max_items,
                    },
                    wait_for_finish=True,
                    timeout_secs=300,
                )
            )

            if result.get("status") == "success":
                jobs = result.get("jobs", [])
                saved, created = save_apify_jobs_to_db(jobs, "linkedin")
                total_saved += saved
                total_companies += created
                logger.info(f"Apify LinkedIn '{query}': {len(jobs)} found, {saved} saved")
            else:
                logger.warning(f"Apify LinkedIn '{query}' failed: {result.get('error')}")

        except Exception as e:
            logger.exception(f"Error scraping LinkedIn for '{query}': {e}")

    return {
        "status": "completed",
        "queries": len(search_queries),
        "jobs_saved": total_saved,
        "companies_created": total_companies,
    }


@shared_task(name="tasks.apify_tasks.scrape_all_apify")
def scrape_all_apify():
    """
    Run all Apify scrapers.

    This is the main orchestrator task that runs Indeed and LinkedIn scrapers.
    """
    logger.info("Starting Apify scrape-all task")

    results = {}

    # Run Indeed scraper
    try:
        results["indeed"] = scrape_apify_indeed()
    except Exception as e:
        logger.exception(f"Indeed scrape failed: {e}")
        results["indeed"] = {"status": "error", "error": str(e)}

    # LinkedIn retired 2026-09-29 (see scrapers/apify/linkedin.py): duplicates of
    # ATS-scraped jobs behind a paid Apify actor. scrape_apify_linkedin stays for
    # manual runs only.

    logger.info(f"Apify scrape-all completed: {results}")
    return results
