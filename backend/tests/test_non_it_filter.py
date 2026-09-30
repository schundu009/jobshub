"""IT/tech-only job list: save-path filter, run outcome, and the non-IT sweep."""
from datetime import datetime, timedelta

import pytest

from models import Job, ScraperRun
from scrapers.base import ScrapedJob, ScrapeResult
from services import scraper_service
from services.scraper_service import save_scraped_jobs
from tasks import maintenance_tasks
from tasks.scraper_tasks import record_scraper_run, save_jobs_into_result


@pytest.fixture(autouse=True)
def retailco_metadata(monkeypatch):
    monkeypatch.setattr(
        scraper_service.ScraperRegistry, "get_metadata",
        classmethod(lambda cls, s: {"company_name": "RetailCo", "careers_url": "https://retail.example/jobs"}),
    )


def job(i, title, **kw):
    return ScrapedJob(title=title, location="Austin, TX", job_url=f"https://retail.example/j/{i}",
                      external_job_id=str(i), posted_date=datetime.utcnow() - timedelta(days=1), **kw)


def test_non_it_jobs_are_skipped_generic_titles_need_a_tech_department(db):
    result = save_scraped_jobs(db, "retailco", [
        job(1, "Site Reliability Engineer"),
        job(2, "Salesforce Developer"),
        job(3, "Store Associate"),
        job(4, "Registered Nurse"),
        job(5, "Shift Lead"),                                          # generic, no tech context
        job(6, "Consultant", department="Information Technology"),     # generic, tech department
    ])
    assert (result.new, result.skipped_non_it) == (3, 3)
    assert {j.title for j in db.query(Job)} == {"Site Reliability Engineer", "Salesforce Developer", "Consultant"}


def test_existing_non_it_row_is_retired_on_rescrape(db):
    save_scraped_jobs(db, "retailco", [job(1, "Platform Engineer")])
    row = db.query(Job).one()
    row.title = "Seasonal Stock & Fulfillment"  # saved before the policy existed
    db.commit()

    save_scraped_jobs(db, "retailco", [job(1, "Seasonal Stock & Fulfillment")])
    assert db.query(Job).one().is_active is False


def test_all_non_it_board_is_a_filtered_run_not_a_failure(db):
    jobs = [job(i, "Warehouse Associate") for i in range(3)]
    result = ScrapeResult(success=True, jobs=jobs, jobs_found=3, started_at=datetime.utcnow(), completed_at=datetime.utcnow())
    save_jobs_into_result(db, "retailco", result)
    record_scraper_run(db, "retailco", result)
    run = db.query(ScraperRun).one()
    assert run.success and "3 skipped_non_it" in (run.error_message or "")


def test_sweep_dry_run_then_apply_leaves_user_jobs_alone(db):
    db.add_all([
        Job(title="DevOps Engineer", source="acme", is_active=True),
        Job(title="Store Associate", source="acme", is_active=True),
        Job(title="Registered Nurse", source="acme", is_active=True),
        Job(title="Store Associate", source="manual", is_active=True),   # user-added: kept
    ])
    db.commit()

    dry = maintenance_tasks.deactivate_non_it_rows(db, apply=False, batch=2)
    assert (dry["checked"], dry["non_it"]) == (3, 2)
    assert db.query(Job).filter(Job.is_active == True).count() == 4  # noqa: E712

    applied = maintenance_tasks.deactivate_non_it_rows(db, apply=True)
    assert applied["non_it"] == 2
    active = sorted((j.title, j.source) for j in db.query(Job).filter(Job.is_active == True))  # noqa: E712
    assert active == [("DevOps Engineer", "acme"), ("Store Associate", "manual")]
    assert maintenance_tasks.deactivate_non_it_rows(db, apply=True)["non_it"] == 0  # idempotent


def test_description_backfill_skips_non_it(db, monkeypatch):
    db.add(Job(title="Store Associate", job_url="https://retail.example/j/9", source="acme", is_active=True))
    db.commit()
    monkeypatch.setattr(maintenance_tasks, "get_db", lambda: db)
    monkeypatch.setattr(maintenance_tasks.ingestion_service, "fetch_job_description_from_url",
                        lambda u: pytest.fail("non-IT jobs must not be fetched"))
    maintenance_tasks.fetch_missing_descriptions(batch_size=5, delay_between=0)
