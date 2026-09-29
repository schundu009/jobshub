"""Shape/value tests for the grouped-query rewrites of hot admin endpoints."""
from datetime import datetime, timedelta

import pytest

from models import Company, Contact, Interview, Job, ScraperConfigDB, ScraperRun
from routes import scrapers as scraper_routes
from services import scraper_service
from utils.security import create_access_token


def headers(user):
    token, _ = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def dataset(db, users):
    owner, stranger = users
    acme = Company(name="Acme")
    globex = Company(name="Globex")
    private_co = Company(name="Owner Co", user_id=owner.id)
    db.add_all([acme, globex, private_co])
    db.flush()
    now = datetime.now()
    db.add_all([
        Job(title="SRE", company_id=acme.id, status="applied", is_active=True, location="Remote",
            excitement_level=4, created_at=now - timedelta(days=1)),
        Job(title="Backend", company_id=acme.id, status="applied", is_active=True, location="Remote",
            excitement_level=2, created_at=now - timedelta(days=1)),
        Job(title="Old", company_id=acme.id, status="rejected", is_active=False, location=None,
            excitement_level=3, created_at=now - timedelta(days=2)),
        Job(title="Frontend", company_id=globex.id, status="wishlist", is_active=True, location="",
            excitement_level=5, created_at=now - timedelta(days=40)),
        # private to owner, attached to a shared company
        Job(title="Mine", company_id=globex.id, status="interviewing", is_active=True,
            user_id=owner.id, location="NYC", excitement_level=3, created_at=now),
    ])
    db.add(Contact(name="Pat", company_id=acme.id))
    db.commit()
    return owner, stranger, acme, globex, private_co


def test_analytics_summary_counts(client, dataset):
    body = client.get("/api/analytics/summary").json()
    assert body["total_jobs"] == 4
    assert body["total_companies"] == 3
    assert body["total_contacts"] == 1
    assert body["status_counts"] == {
        "wishlist": 1, "applied": 2, "interviewing": 1, "offer": 0, "rejected": 0, "withdrawn": 0,
    }
    assert body["upcoming_interviews"] == 0
    assert len(body["recent_activity"]) == 5
    first = body["recent_activity"][0]
    assert set(first) == {"id", "title", "company_name", "status", "created_at"}
    assert first["title"] == "Mine" and first["company_name"] == "Globex"


def test_analytics_by_company(client, dataset):
    _, _, acme, globex, _ = dataset
    companies = client.get("/api/analytics/by-company").json()["companies"]
    assert companies == [
        {"company_id": acme.id, "company_name": "Acme", "job_count": 3,
         "status_breakdown": {"applied": 2, "rejected": 1}},
        {"company_id": globex.id, "company_name": "Globex", "job_count": 2,
         "status_breakdown": {"wishlist": 1, "interviewing": 1}},
    ]


def test_analytics_by_location(client, dataset):
    locations = client.get("/api/analytics/by-location").json()["locations"]
    # None and "" both fold into "Not specified"; sorted by count descending
    assert sorted(locations[:2], key=lambda x: x["location"]) == [
        {"location": "Not specified", "count": 2}, {"location": "Remote", "count": 2}]
    assert locations[2:] == [{"location": "NYC", "count": 1}]


def test_analytics_timeline_status_and_rates(client, dataset):
    timeline = client.get("/api/analytics/timeline").json()["timeline"]
    assert len(timeline) >= 30
    assert sum(d["count"] for d in timeline) == 4  # 40-day-old job excluded
    day = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert {"date": day, "count": 2} in timeline

    breakdown = client.get("/api/analytics/status-breakdown").json()
    assert breakdown["total"] == 5
    assert {"status": "applied", "count": 2, "percentage": 40.0} in breakdown["breakdown"]

    rates = client.get("/api/analytics/response-rate").json()
    assert rates["total_applied"] == 4 and rates["got_interview"] == 1 and rates["rejected"] == 1

    excitement = client.get("/api/analytics/excitement-distribution").json()
    assert [d["count"] for d in excitement["distribution"]] == [0, 1, 2, 1, 1]
    assert excitement["average"] == 3.4


def test_interview_stats(client, dataset, db):
    job = db.query(Job).filter(Job.title == "SRE").one()
    db.add_all([
        Interview(job_id=job.id, interview_date=datetime.now() + timedelta(days=2),
                  interview_type="technical", outcome="pending"),
        Interview(job_id=job.id, interview_date=datetime.now() - timedelta(days=2),
                  interview_type="phone_screen", outcome="passed"),
    ])
    db.commit()
    body = client.get("/api/analytics/interview-stats").json()
    assert body["total_interviews"] == 2
    assert body["by_outcome"] == {"pending": 1, "passed": 1, "failed": 0, "cancelled": 0}
    assert body["by_type"]["technical"] == 1 and body["by_type"]["final"] == 0
    assert body["upcoming"][0]["company_name"] == "Acme"


def test_companies_job_counts_respect_visibility(client, dataset):
    owner, stranger, acme, globex, private_co = dataset
    mine = {c["id"]: c for c in client.get("/api/companies", headers=headers(owner)).json()}
    theirs = {c["id"]: c for c in client.get("/api/companies", headers=headers(stranger)).json()}
    assert mine[acme.id]["job_count"] == 3
    assert mine[globex.id]["job_count"] == 2  # includes owner's private job
    assert mine[private_co.id]["job_count"] == 0
    assert theirs[globex.id]["job_count"] == 1
    assert private_co.id not in theirs
    assert set(mine[acme.id]) == {"id", "name", "website", "industry", "size", "location",
                                  "notes", "created_at", "job_count"}


def test_scraper_status_bulk_matches_per_scraper_stats(client, dataset, db, monkeypatch):
    owner = dataset[0]
    meta = {"acme": {"company_name": "ACME"}, "globex": {"company_name": "Globex"},
            "nobody": {"company_name": "Nobody Inc"}}
    monkeypatch.setattr(scraper_routes.ScraperRegistry, "list_slugs", classmethod(lambda cls: list(meta)))
    monkeypatch.setattr(scraper_service.ScraperRegistry, "get_metadata", classmethod(lambda cls, s: meta.get(s)))

    now = datetime.now()
    db.add(ScraperConfigDB(company_slug="acme", is_enabled=False, consecutive_failures=2,
                           total_runs=7, last_success_at=now - timedelta(days=1)))
    runs = [ScraperRun(company_slug="acme", success=True, run_at=now - timedelta(hours=1))]
    runs.append(ScraperRun(company_slug="acme", success=False, error_message="timeout",
                           run_at=now - timedelta(hours=2)))
    runs.append(ScraperRun(company_slug="acme", success=False, error_message="older",
                           run_at=now - timedelta(hours=3)))
    # globex: failure only beyond the 10 most recent runs -> no last_error
    runs.append(ScraperRun(company_slug="globex", success=False, error_message="ancient",
                           run_at=now - timedelta(days=30)))
    runs += [ScraperRun(company_slug="globex", success=True, run_at=now - timedelta(hours=i))
             for i in range(10)]
    db.add_all(runs)
    db.commit()

    response = client.get("/api/scrapers/status", headers=headers(owner))
    assert response.status_code == 200
    body = response.json()
    assert [s["company_slug"] for s in body] == ["acme", "globex", "nobody"]

    for row in body:
        expected = scraper_service.get_scraper_stats(db, row["company_slug"])
        expected.pop("recent_runs")
        assert row == expected

    acme = body[0]
    assert acme["is_enabled"] is False and acme["total_runs"] == 7
    assert acme["last_error"] == "timeout"
    assert acme["active_jobs"] == 2 and acme["total_jobs"] == 3
    assert body[1]["last_error"] is None
    assert body[2]["active_jobs"] == 0 and body[2]["is_enabled"] is True
