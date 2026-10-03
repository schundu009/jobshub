"""Workday jobs: location from the job path, and descriptions/locations from the cxs detail API."""
import pytest

from models import Job
from scrapers.custom.remaining_scrapers import _workday_location
from services import ingestion_service
from tasks import maintenance_tasks


@pytest.mark.parametrize("text,path,expected", [
    ("", "/job/Madrid/Arquitecto-Devops_R00359220-1", "Madrid"),       # Accenture: no locationsText
    ("3 Locations", "/job/Hyderabad/Engineer_R1", "Hyderabad (+2 more)"),
    ("1 Location", "/job/Austin/Engineer_R1", "Austin"),
    ("2 Locations", "/job/US-CA-San-Jose/SRE_R1", "US CA San Jose (+1 more)"),
    ("Austin, TX", "/job/Austin/Engineer_R1", "Austin, TX"),         # real text wins
    ("", "", ""),
    ("2 Locations", "weird", "2 Locations"),                         # nothing better to offer
])
def test_workday_location(text, path, expected):
    assert _workday_location(text, path) == expected


@pytest.mark.parametrize("url,api", [
    ("https://accenture.wd103.myworkdayjobs.com/accenturecareers/job/Madrid/Arquitecto_R00359220-1",
     "https://accenture.wd103.myworkdayjobs.com/wday/cxs/accenture/accenturecareers/job/Madrid/Arquitecto_R00359220-1"),
    ("https://acme.wd5.myworkdayjobs.com/en-US/External/job/Austin-TX/SRE_R1?src=x",
     "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/External/job/Austin-TX/SRE_R1"),
    ("https://boards.greenhouse.io/acme/jobs/1", None),
])
def test_workday_detail_api_url(url, api):
    assert ingestion_service.workday_detail_api_url(url) == api


def test_workday_posting_location_lists_all_sites_and_country():
    info = {"location": "Madrid", "additionalLocations": ["Barcelona", "Madrid"], "country": {"descriptor": "Spain"}}
    assert ingestion_service.workday_posting_location(info) == "Madrid; Barcelona, Spain"
    assert ingestion_service.workday_posting_location({}) == ""


def test_backfill_fills_workday_description_location_and_country(db, monkeypatch):
    url = "https://accenture.wd103.myworkdayjobs.com/accenturecareers/job/Madrid/Arquitecto_R00359220-1"
    job = Job(title="Arquitecto Devops", job_url=url, location="", source="accenture", is_active=True)
    db.add(job)
    db.commit()
    monkeypatch.setattr(maintenance_tasks, "get_db", lambda: db)
    monkeypatch.setattr(ingestion_service, "fetch_workday_posting", lambda u: (200, {
        "jobDescription": "<p>" + "Build CI/CD with GitHub Actions. " * 10 + "</p>",
        "location": "Madrid", "country": {"descriptor": "Spain"},
    }))
    monkeypatch.setattr(ingestion_service, "fetch_job_description_from_url",
                        lambda u: pytest.fail("Workday URLs must use the detail API"))

    result = maintenance_tasks.fetch_missing_descriptions(batch_size=10, delay_between=0)

    assert result["updated"] == 1
    job = db.query(Job).get(job.id)
    assert "GitHub Actions" in job.job_description
    assert job.location == "Madrid, Spain" and job.country_codes == ",ES,"


def test_backfill_rotates_jobs_it_cannot_fetch(db, monkeypatch):
    a = Job(title="Data Engineer A", job_url="https://example.com/a", source="x", is_active=True)
    b = Job(title="Data Engineer B", job_url="https://example.com/b", source="x", is_active=True)
    db.add_all([a, b])
    db.commit()
    monkeypatch.setattr(maintenance_tasks, "get_db", lambda: db)
    seen = []
    monkeypatch.setattr(ingestion_service, "fetch_job_description_from_url", lambda u: seen.append(u) or "")

    maintenance_tasks.fetch_missing_descriptions(batch_size=1, delay_between=0)
    maintenance_tasks.fetch_missing_descriptions(batch_size=1, delay_between=0)

    assert sorted(seen) == ["https://example.com/a", "https://example.com/b"]  # not the same job twice


def test_backfill_reaches_live_postings_the_scraper_keeps_touching(db, monkeypatch):
    # A live posting the scraper re-listed a minute ago (updated_at fresh) and a
    # stale one nobody touched for weeks. Ordering by updated_at put the stale
    # one first every run and the live one never; the backfill's own attempt
    # time puts never-tried jobs first, the most recently listed of them first.
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    live = Job(title="Data Engineer Live", job_url="https://example.com/live", source="x", is_active=True,
               last_seen_at=now, updated_at=now)
    stale = Job(title="Data Engineer Stale", job_url="https://example.com/stale", source="x", is_active=True,
                last_seen_at=now - timedelta(days=3), updated_at=now - timedelta(days=20))
    db.add_all([live, stale])
    db.commit()
    monkeypatch.setattr(maintenance_tasks, "get_db", lambda: db)
    seen = []
    monkeypatch.setattr(ingestion_service, "fetch_job_description_from_url", lambda u: seen.append(u) or "")
    maintenance_tasks.fetch_missing_descriptions(batch_size=1, delay_between=0)
    assert seen == ["https://example.com/live"]


def test_backfill_retires_a_closed_workday_posting(db, monkeypatch):
    url = "https://intel.wd1.myworkdayjobs.com/External/job/US-Texas-Austin/Memory-Circuit-Design-Engineer_JR0286626"
    job = Job(title="Memory Circuit Design Engineer", job_url=url, source="intel", is_active=True)
    db.add(job)
    db.commit()
    monkeypatch.setattr(maintenance_tasks, "get_db", lambda: db)
    monkeypatch.setattr(ingestion_service, "fetch_workday_posting", lambda u: (404, {}))
    result = maintenance_tasks.fetch_missing_descriptions(batch_size=5, delay_between=0)
    assert result["closed"] == 1 and result["failed"] == 0
    assert db.query(Job).get(job.id).is_active is False


def test_backfill_gives_up_after_repeated_failures_and_skips_meta(db, monkeypatch):
    from datetime import datetime, timedelta
    job = Job(title="Data Engineer", job_url="https://example.com/x", source="x", is_active=True)
    meta = Job(title="Data Engineer", job_url="https://www.metacareers.com/profile/job_details/1/", source="meta", is_active=True)
    db.add_all([job, meta])
    db.commit()
    monkeypatch.setattr(maintenance_tasks, "get_db", lambda: db)
    seen = []
    monkeypatch.setattr(ingestion_service, "fetch_job_description_from_url", lambda u: seen.append(u) or "")
    for _ in range(maintenance_tasks.DESCRIPTION_MAX_FAILURES + 2):
        maintenance_tasks.fetch_missing_descriptions(batch_size=5, delay_between=0)
        # Let the retry wait pass between runs.
        j = db.query(Job).get(job.id)
        if j.description_fetch_attempted_at:
            j.description_fetch_attempted_at -= timedelta(hours=maintenance_tasks.DESCRIPTION_RETRY_HOURS + 1)
            db.commit()
    assert seen.count("https://example.com/x") == maintenance_tasks.DESCRIPTION_MAX_FAILURES
    assert all("metacareers" not in u for u in seen)


def test_opening_a_job_without_a_description_fetches_it(db, client, monkeypatch):
    """POST /api/jobs/{id}/description fetches and stores it once; the cooldown stops a second request."""
    job = Job(title="DevOps Engineer", job_url="https://example.com/devops", is_active=True, source="greenhouse")
    db.add(job)
    db.commit()
    calls = []
    monkeypatch.setattr(ingestion_service, "fetch_job_description_from_url",
                        lambda u: calls.append(u) or "Build and run the platform. " * 10)
    r = client.post(f"/api/jobs/{job.id}/description")
    assert r.status_code == 200
    assert r.json()["description_status"] == "stored"
    assert r.json()["job_description"].startswith("Build and run the platform.")
    assert client.post(f"/api/jobs/{job.id}/description").json()["description_status"] == "stored"
    assert len(calls) == 1
