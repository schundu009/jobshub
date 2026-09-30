"""Save path: fork-safe DB pool, per-row recovery, contract routing, freshness model."""
import weakref
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from contracts.models import ContractJob
from database import Base
from models import Job
from scrapers.base import ScrapedJob
from services import scraper_service
from services.scraper_service import save_scraped_jobs

META = {"bigco": {"company_name": "BigCo", "careers_url": "https://bigco.example/jobs", "category": "custom"},
        "agency": {"company_name": "Agency Staffing", "careers_url": "https://agency.example", "category": "staffing"}}


@pytest.fixture(autouse=True)
def registry_metadata(monkeypatch):
    monkeypatch.setattr(scraper_service.ScraperRegistry, "get_metadata",
                        classmethod(lambda cls, s: META.get(s, META["bigco"])))


def job(i, **kw):
    fields = dict(title=f"Engineer {i}", location="Austin, TX", job_url=f"https://bigco.example/j/{i}",
                  external_job_id=str(i), posted_date=datetime.utcnow() - timedelta(days=1))
    fields.update(kw)
    return ScrapedJob(**fields)


# ------------------------------------------------------------------ celery fork safety

def test_worker_process_init_disposes_inherited_pool(monkeypatch):
    from celery.signals import worker_process_init
    import celery_app
    import database

    handler = celery_app._reset_db_pool_after_fork
    receivers = [r() if isinstance(r, weakref.ReferenceType) else r for _, r in worker_process_init.receivers]
    assert handler in receivers

    calls = []

    class FakeEngine:
        def dispose(self, close=True):
            calls.append(close)

    monkeypatch.setattr(database, "engine", FakeEngine())
    handler()
    assert calls == [False]  # drop the pool without closing the parent's sockets


# ------------------------------------------------------------------ per-row recovery

def test_one_broken_row_does_not_poison_the_batch(tmp_path):
    """A row whose INSERT kills the connection (psycopg2 'lost synchronization',
    then PendingRollbackError) costs that row only; the other 499 are saved."""
    engine = create_engine(f"sqlite:///{tmp_path / 'jobs.db'}")
    Base.metadata.create_all(engine)

    def explode(mapper, connection, target):
        if target.external_job_id == "250":
            connection.invalidate()
            raise OperationalError("INSERT INTO jobs", {}, Exception("lost synchronization with server"))

    event.listen(Job, "before_insert", explode)
    try:
        with Session(engine) as db:
            result = save_scraped_jobs(db, "bigco", [job(i) for i in range(500)])
            assert (result.new, result.errors) == (499, 1)
            assert "OperationalError" in result.first_error and result.commit_error is None
        with Session(engine) as db:
            ids = {j.external_job_id for j in db.query(Job).all()}
            assert len(ids) == 499 and "250" not in ids
    finally:
        event.remove(Job, "before_insert", explode)
        engine.dispose()


def test_integrity_error_row_counts_as_duplicate(db, monkeypatch):
    save_scraped_jobs(db, "bigco", [job(1)])
    # Force the existing-row lookup to miss so the insert hits the unique index.
    monkeypatch.setattr(scraper_service, "_find_reposts", lambda *a, **k: {})
    real_query = db.query

    class Miss:
        def __init__(self, q):
            self.q = q

        def filter(self, *a, **k):
            return self

        def all(self):
            return []

    monkeypatch.setattr(db, "query", lambda *a, **k: Miss(None) if a and a[0] is Job else real_query(*a, **k))
    result = save_scraped_jobs(db, "bigco", [job(1), job(2)])
    monkeypatch.setattr(db, "query", real_query)
    assert (result.new, result.duplicates, result.errors) == (1, 1, 0)


# ------------------------------------------------------------------ contract routing

def test_contract_postings_go_to_contract_jobs(db):
    result = save_scraped_jobs(db, "bigco", [
        job(1),
        job(2, title="Java Developer (Contract)", job_description="6 month contract, W2 only, $70/hr"),
        job(3, title="Contracts Systems Analyst", job_description="Manage vendor contracts."),  # a role, not terms
        job(4, title="Data Engineer", employment_type_raw="Contract to Hire"),
    ])
    assert (result.new, result.contracts) == (2, 2)
    assert {j.external_job_id for j in db.query(Job).all()} == {"1", "3"}
    rows = {c.external_job_id: c for c in db.query(ContractJob).all()}
    assert set(rows) == {"2", "4"}
    assert rows["2"].source_type == "company_board" and rows["2"].company_id is not None
    assert rows["2"].tax_terms == ["w2"] and rows["2"].pay_rate_min == 70 and rows["2"].contract_duration_months == 6
    assert rows["4"].employment_type == "contract_to_hire"


def test_existing_job_reclassified_as_contract_moves_out(db):
    save_scraped_jobs(db, "bigco", [job(1, title="Data Engineer")])
    save_scraped_jobs(db, "bigco", [job(1, title="Data Engineer", employment_type_raw="Contract")])
    row = db.query(Job).one()
    assert row.is_active is False and row.employment_type == "contract"
    assert db.query(ContractJob).count() == 1


def test_staffing_scrapers_never_write_jobs(db):
    result = save_scraped_jobs(db, "agency", [job(1, title="Python Developer"), job(2, title="Direct Hire Accountant",
                                                                                   employment_type_raw="Permanent")])
    assert result.new == 0 and result.contracts == 1
    assert db.query(Job).count() == 0
    row = db.query(ContractJob).one()
    assert row.agency_name == "Agency Staffing" and row.source_type == "staffing"


# ------------------------------------------------------------------ freshness

def test_first_and_last_seen_and_quiet_rescrape(db):
    posted = (datetime.utcnow() - timedelta(days=3)).replace(microsecond=0)
    save_scraped_jobs(db, "bigco", [job(1, posted_date=posted)])
    row = db.query(Job).one()
    first_seen, updated = row.first_seen_at, row.updated_at
    assert row.last_seen_at == first_seen and row.reposted_count == 0 and row.is_evergreen is False

    save_scraped_jobs(db, "bigco", [job(1, posted_date=posted)])  # same content
    db.refresh(row)
    assert row.first_seen_at == first_seen and row.last_seen_at > first_seen
    assert row.updated_at == updated  # last_seen_at alone doesn't bump updated_at


def test_redated_posting_keeps_original_listing_date_and_counts_repost(db):
    original = datetime.utcnow() - timedelta(days=20)
    save_scraped_jobs(db, "bigco", [job(1, posted_date=original)])
    save_scraped_jobs(db, "bigco", [job(1, posted_date=datetime.utcnow())])  # board re-dates it
    row = db.query(Job).one()
    assert row.effective_posted_at == original and row.reposted_count == 1


def test_reposted_under_new_id_becomes_evergreen(db):
    save_scraped_jobs(db, "bigco", [job(1, title="Site Reliability Engineer")])
    for n, new_id in enumerate(("2", "3"), start=1):
        db.query(Job).filter(Job.is_active == True).update({"is_active": False})  # noqa: E712 - it disappeared
        db.commit()
        save_scraped_jobs(db, "bigco", [job(new_id, title="Site Reliability Engineer")])
        row = db.query(Job).filter(Job.external_job_id == new_id).one()
        assert row.reposted_count == n
    assert row.is_evergreen and row.evergreen_reason == "reposted"


def test_talent_pool_posting_is_evergreen(db):
    save_scraped_jobs(db, "bigco", [job(1, title="Software Engineer - Talent Community")])
    row = db.query(Job).one()
    assert row.is_evergreen and row.evergreen_reason == "talent_pool"


def test_stale_task_uses_last_seen(db, monkeypatch):
    from tasks import maintenance_tasks
    save_scraped_jobs(db, "bigco", [job(1), job(2)])
    old = datetime.utcnow() - timedelta(days=30)
    db.query(Job).update({"updated_at": old})
    db.query(Job).filter(Job.external_job_id == "2").update({"last_seen_at": old})
    db.commit()
    monkeypatch.setattr(maintenance_tasks, "get_db", lambda: db)
    monkeypatch.setattr(db, "close", lambda: None)
    maintenance_tasks.mark_stale_jobs_inactive(days=14)
    active = {j.external_job_id: j.is_active for j in db.query(Job).all()}
    assert active == {"1": True, "2": False}


def test_seasonal_direct_hire_stays_in_jobs_but_staffing_temp_moves(db):
    result = save_scraped_jobs(db, "bigco", [
        job(1, title="Seasonal IT Support Technician", job_description="Holiday season. $25/hr"),
        job(2, title="IT Help Desk Technician (Seasonal - Fixed Term)", employment_type_raw="Seasonal - Fixed Term"),
        job(3, title="Temporary Software Engineer", job_description="Temp via TEKsystems, W2 $70/hr"),
    ])
    assert (result.new, result.contracts) == (2, 1)
    kept = {j.external_job_id: j.employment_type for j in db.query(Job)}
    assert kept == {"1": "temporary", "2": "temporary"}
    assert db.query(ContractJob).one().external_job_id == "3"


def test_temporary_jobs_are_listed_in_api(client, db):
    save_scraped_jobs(db, "bigco", [job(1, title="Seasonal IT Support Technician")])
    body = client.get("/api/jobs?all=true").json()
    assert [(j["title"], j["employment_type"]) for j in body["jobs"]] == [("Seasonal IT Support Technician", "temporary")]
