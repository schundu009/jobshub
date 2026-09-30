"""save_scraped_jobs: big batches, skip reasons, sanitizing, and save_failed runs."""
from datetime import datetime, timedelta, timezone

import pytest

from models import AppSetting, Job, ScraperConfigDB, ScraperRun
from scrapers.base import ScrapedJob, ScrapeResult
from services import scraper_service
from services.scraper_service import SaveResult, save_scraped_jobs
from tasks.scraper_tasks import record_scraper_run, save_jobs_into_result


@pytest.fixture(autouse=True)
def bigco_metadata(monkeypatch):
    monkeypatch.setattr(
        scraper_service.ScraperRegistry, "get_metadata",
        classmethod(lambda cls, s: {"company_name": "BigCo", "careers_url": "https://bigco.example/jobs"}),
    )


def job(i, **kw):
    fields = dict(title=f"Engineer {i}", location="Remote", job_url=f"https://bigco.example/j/{i}",
                  external_job_id=str(i), posted_date=datetime.utcnow() - timedelta(days=1))
    fields.update(kw)
    return ScrapedJob(**fields)


def test_large_batch_is_saved(db):
    # The old per-job begin_nested() nested ~N savepoints; commit then hit
    # "maximum recursion depth exceeded" and the whole batch was dropped.
    jobs = [job(i) for i in range(1500)]
    result = save_scraped_jobs(db, "bigco", jobs)
    assert (result.new, result.updated) == (1500, 0)
    assert db.query(Job).filter(Job.source == "bigco").count() == 1500

    again = save_scraped_jobs(db, "bigco", jobs)
    assert tuple(again) == (0, 1500)  # still unpacks like the old tuple
    assert db.query(Job).count() == 1500


def test_skip_reasons_are_counted(db):
    # Aggregator feeds keep the age cut-off (company boards don't; see below).
    now = datetime.utcnow()
    jobs = [
        job(1),                                          # saved
        job(2, posted_date=None),                        # unknown date -> kept
        job(3, posted_date=datetime(1970, 1, 1)),        # epoch artefact -> unknown -> kept
        job(4, posted_date=now - timedelta(days=90)),    # real, old -> skipped_old
        job(5, title="   "),                             # skipped_invalid
        job(1, title="Engineer 1 (dup)"),                # same id in batch -> duplicate
        job(6, posted_date=datetime.now(timezone(timedelta(hours=-7)))),  # tz-aware -> kept
    ]
    result = save_scraped_jobs(db, "themuse", jobs)
    assert result.as_dict() == {
        "new": 4, "updated": 0, "skipped_old": 1, "skipped_invalid": 1,
        "duplicates": 1, "errors": 0, "contracts": 0, "first_error": None, "commit_error": None,
    }
    saved = {j.external_job_id: j for j in db.query(Job).all()}
    assert set(saved) == {"1", "2", "3", "6"}
    assert saved["2"].posted_date is None and saved["3"].posted_date is None
    assert saved["6"].posted_date.tzinfo is None
    assert "skipped_old" in result.summary()


def test_age_cutoff_follows_setting(db):
    db.add(AppSetting(key="max_job_age_days", value="7"))
    db.commit()
    result = save_scraped_jobs(db, "themuse", [job(1, posted_date=datetime.utcnow() - timedelta(days=10))])
    assert (result.new, result.skipped_old) == (0, 1)


def test_company_board_keeps_old_postings_while_listed(db):
    old = datetime.utcnow() - timedelta(days=200)
    result = save_scraped_jobs(db, "bigco", [job(1, posted_date=old)])
    assert (result.new, result.skipped_old) == (1, 0)
    row = db.query(Job).one()
    assert row.effective_posted_at == old and row.is_evergreen and row.evergreen_reason == "long_listed"


def test_values_are_fitted_to_columns(db):
    long_loc = "; ".join(f"City {i}, Country" for i in range(60))  # > 500 chars (Google)
    result = save_scraped_jobs(db, "bigco", [
        job(1, location=long_loc, title="Eng\x00ineer", department="D" * 400,
            salary_min=150000200000, salary_max=180000),
        job("x" * 300),
    ])
    assert result.new == 2
    row = db.query(Job).filter(Job.external_job_id == "1").one()
    assert len(row.location) <= 500 and row.title == "Engineer" and len(row.department) <= 255
    assert row.salary_min is None and row.salary_max == 180000
    assert db.query(Job).filter(Job.external_job_id != "1").one().external_job_id.__len__() <= 255


def test_commit_failure_is_reported(db, monkeypatch):
    def boom():
        raise RuntimeError("db went away")
    monkeypatch.setattr(db, "commit", boom)
    result = save_scraped_jobs(db, "bigco", [job(1)])
    assert result.saved == 0 and "db went away" in result.commit_error


# ------------------------------------------------------------ run recording

def _result(n):
    now = datetime.utcnow()
    return ScrapeResult(success=True, jobs=[job(i) for i in range(n)], started_at=now, completed_at=now)


def test_all_skipped_old_is_a_successful_run(db, monkeypatch):
    # Policy, not failure: every job filtered by age -> success with a note.
    monkeypatch.setattr(scraper_service, "save_scraped_jobs",
                        lambda *a, **k: SaveResult(skipped_old=3))
    result = _result(3)
    save_jobs_into_result(db, "bigco", result)
    record_scraper_run(db, "bigco", result)
    run = db.query(ScraperRun).one()
    assert run.success and run.error_type is None
    assert run.error_message == "saved: 0 new, 0 updated, 3 skipped_old"
    assert db.query(ScraperConfigDB).one().consecutive_failures == 0


@pytest.mark.parametrize("stats", [SaveResult(errors=3, first_error="boom"), SaveResult(commit_error="gone")])
def test_found_but_nothing_saved_through_errors_is_a_failed_run(db, monkeypatch, stats):
    monkeypatch.setattr(scraper_service, "save_scraped_jobs", lambda *a, **k: stats)
    result = _result(3)
    save_jobs_into_result(db, "bigco", result)
    record_scraper_run(db, "bigco", result)
    run = db.query(ScraperRun).one()
    assert not run.success and run.error_type == "save_failed"
    assert "3 jobs found, 0 saved" in run.error_message
    assert db.query(ScraperConfigDB).one().consecutive_failures == 1


def test_save_exception_is_a_failed_run(db, monkeypatch):
    def raise_(*a, **k):
        raise ValueError("bad batch")
    monkeypatch.setattr(scraper_service, "save_scraped_jobs", raise_)
    result = _result(2)
    save_jobs_into_result(db, "bigco", result)
    record_scraper_run(db, "bigco", result)
    run = db.query(ScraperRun).one()
    assert run.error_type == "save_failed" and "bad batch" in run.error_message


def test_successful_run_keeps_skip_breakdown(db):
    result = _result(2)
    result.jobs.append(job(99, posted_date=datetime.utcnow() - timedelta(days=60)))
    result.jobs_found = 3
    save_jobs_into_result(db, "themuse", result)
    record_scraper_run(db, "themuse", result)
    run = db.query(ScraperRun).one()
    assert run.success and (run.jobs_new, run.jobs_found) == (2, 3)
    assert run.error_type is None and "1 skipped_old" in run.error_message


def test_runs_without_a_save_attempt_are_untouched(db):
    now = datetime.utcnow()
    record_scraper_run(db, "bigco", ScrapeResult(success=True, jobs_found=5, started_at=now, completed_at=now))
    assert db.query(ScraperRun).one().success
