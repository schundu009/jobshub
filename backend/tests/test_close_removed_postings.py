"""Postings a complete board scrape no longer lists are closed after two runs."""
import asyncio
from datetime import datetime

import pytest

from models import Job
from scrapers.base import HTTPScraper, ScrapedJob, ScrapeResult, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import SmartRecruitersMixin, WorkdayMixin
from services import scraper_service
from tasks.scraper_tasks import save_jobs_into_result

META = {"acme": {"company_name": "Acme", "careers_url": "https://acme.example", "category": "custom"},
        "themuse": {"company_name": "The Muse", "careers_url": "https://themuse.example", "category": "other"}}


@pytest.fixture(autouse=True)
def registry(monkeypatch):
    monkeypatch.setattr(scraper_service.ScraperRegistry, "get_metadata", classmethod(lambda cls, s: META.get(s)))


def scrape(db, ids, complete=True, success=True, slug="acme"):
    now = datetime.utcnow()
    jobs = [ScrapedJob(title=f"Software Engineer {i}", location="Remote", job_url=f"https://acme/{i}",
                       external_job_id=str(i), posted_date=now) for i in ids]
    result = ScrapeResult(success=success, jobs=jobs, complete=complete)
    save_jobs_into_result(db, slug, result)
    return result


def state(db, ext="3"):
    job = db.query(Job).filter(Job.external_job_id == ext).one()
    db.refresh(job)
    return job.is_active, job.missed_runs


def test_closed_after_two_complete_runs_and_reopened_when_back(db):
    scrape(db, [1, 2, 3])
    assert state(db) == (True, 0)
    scrape(db, [1, 2])
    assert state(db) == (True, 1)
    result = scrape(db, [1, 2])
    assert state(db) == (False, 2) and result.save_stats["closed"] == 1
    assert state(db, "1") == (True, 0)
    scrape(db, [1, 2, 3])
    assert state(db) == (True, 0)


def test_a_miss_is_forgiven_when_the_posting_returns(db):
    scrape(db, [1, 2, 3])
    scrape(db, [1, 2])
    scrape(db, [1, 2, 3])
    scrape(db, [1, 2])
    assert state(db) == (True, 1)


def test_bookkeeping_keeps_updated_at(db):
    scrape(db, [1, 2, 3])
    before = db.query(Job.updated_at).filter(Job.external_job_id == "3").scalar()
    scrape(db, [1, 2])
    assert db.query(Job.updated_at).filter(Job.external_job_id == "3").scalar() == before


@pytest.mark.parametrize("kwargs", [
    {"success": True, "complete": False},   # page/job cap, time budget, partial
    {"success": False, "complete": True},   # failed run
])
def test_guarded_runs_never_count_misses(db, kwargs):
    scrape(db, [1, 2, 3])
    listed = [ScrapedJob("Software Engineer 1", "Remote", "https://acme/1", "1"),
              ScrapedJob("Software Engineer 2", "Remote", "https://acme/2", "2")]
    for _ in range(3):
        assert scraper_service.close_removed_postings(db, "acme", ScrapeResult(jobs=listed, **kwargs)) == 0
    assert state(db) == (True, 0)


def test_empty_save_failure_aggregator_and_owned_jobs_are_left_alone(db):
    scrape(db, [1, 2, 3])
    empty = ScrapeResult(success=True, jobs=[], complete=True)
    assert scraper_service.close_removed_postings(db, "acme", empty) == 0
    broken = ScrapeResult(success=True, jobs=[ScrapedJob("x", "", "", "1")], complete=True,
                          save_stats={"commit_error": "OperationalError"})
    for _ in range(3):
        assert scraper_service.close_removed_postings(db, "acme", broken) == 0
    assert state(db) == (True, 0)

    scrape(db, [10, 11], slug="themuse")
    for _ in range(3):
        scrape(db, [10], slug="themuse")
    assert state(db, "11")[0] is True

    owned = db.query(Job).filter(Job.external_job_id == "3").one()
    owned.user_id = 1
    db.commit()
    for _ in range(3):
        scrape(db, [1, 2])
    assert state(db) == (True, 0)


# ------------------------------------------------------------------ which results are complete

def _cfg(slug):
    return ScraperConfig(company_slug=slug, company_name=slug, careers_url="https://x", scraper_type=ScraperType.HTTP)


class WD(WorkdayMixin, HTTPScraper):
    config = _cfg("wd")
    API_URL = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Careers/jobs"


class SR(SmartRecruitersMixin, HTTPScraper):
    config = _cfg("sr")
    API_URL = "https://api.smartrecruiters.com/v1/companies/Acme/postings"
    COMPANY_ID = "Acme"


def _run(scraper, pages):
    calls = iter(pages)

    async def fetch_json(url, method="GET", params=None, json_data=None, **_):
        return next(calls)
    scraper.fetch_json = fetch_json
    return asyncio.run(scraper.scrape())


def _wd_page(n, start=0):
    return {"jobPostings": [{"title": f"t{start + i}", "externalPath": f"/job/x/t_R{start + i}",
                             "bulletFields": [f"R{start + i}"]} for i in range(n)]}


def test_workday_completeness(monkeypatch):
    assert _run(WD(), [_wd_page(20), _wd_page(5, 20)]).complete is True
    assert _run(WD(), [_wd_page(20), {"jobPostings": []}]).complete is True
    assert _run(WD(), [_wd_page(20), None]).complete is False
    monkeypatch.setattr(WD, "MAX_JOBS", 40)
    capped = _run(WD(), [_wd_page(20), _wd_page(20, 20), _wd_page(20, 40)])
    assert capped.complete is False and len(capped.jobs) == 40


def test_smartrecruiters_completeness():
    page = {"content": [{"id": "1", "name": "SRE", "location": {}}], "totalFound": 1}
    assert _run(SR(), [page]).complete is True
    full = {"content": [{"id": str(i), "name": "SRE", "location": {}} for i in range(100)], "totalFound": 250}
    assert _run(SR(), [full, None]).complete is False


def test_most_of_a_board_vanishing_closes_nothing(db):
    """A changed job-id format looks like every posting removed: leave them open."""
    scrape(db, list(range(1, 31)))
    scrape(db, [1, 2, 3])
    scrape(db, [1, 2, 3])
    assert state(db, "20") == (True, 0)
