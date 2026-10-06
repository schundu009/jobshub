"""Per-board scraper health: /api/scrapers/health and the alert that lists broken boards."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from models import JobBoard, ScraperConfigDB, ScraperRun, User
from scrapers.registry import ScraperRegistry
from services import scraper_health
from utils.security import create_access_token, hash_password

NOW = datetime(2026, 10, 3, 12, 0, 0)

CODED = {
    "fresh": SimpleNamespace(API_URL="https://boards-api.greenhouse.io/v1/boards/fresh/jobs"),
    "flaky": SimpleNamespace(API_URL="https://api.lever.co/v0/postings/flaky?mode=json"),
    "dead": SimpleNamespace(API_URL="https://dead.wd5.myworkdayjobs.com/wday/cxs/dead/Careers/jobs"),
    "never": SimpleNamespace(API_URL="https://careers.oracle.example/api"),
    "off": SimpleNamespace(API_URL="https://boards-api.greenhouse.io/v1/boards/off/jobs"),
}


@pytest.fixture
def registry(db, monkeypatch):
    import database
    from sqlalchemy.orm import sessionmaker
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=db.get_bind()))
    db.add(JobBoard(company_name="Board Co", slug="boardco", ats="ashby", board="boardco"))
    db.commit()
    real_get, real_meta = ScraperRegistry.get.__func__, ScraperRegistry.get_metadata.__func__
    monkeypatch.setattr(ScraperRegistry, "list_slugs", classmethod(lambda cls: list(CODED)))
    monkeypatch.setattr(ScraperRegistry, "has_coded", classmethod(lambda cls, s: s in CODED))
    monkeypatch.setattr(ScraperRegistry, "get", classmethod(
        lambda cls, s: CODED.get(s) or real_get(cls, s)))
    monkeypatch.setattr(ScraperRegistry, "get_metadata", classmethod(
        lambda cls, s: {"company_name": s.title()} if s in CODED else real_meta(cls, s)))


def run(db, slug, hours_ago, success=True, jobs=0, error=None):
    db.add(ScraperRun(company_slug=slug, success=success, jobs_found=jobs, error_message=error,
                      run_at=NOW - timedelta(hours=hours_ago)))


@pytest.fixture
def history(db, registry):
    run(db, "fresh", 8, jobs=12)
    run(db, "fresh", 2, jobs=10)
    run(db, "flaky", 10, jobs=5)
    for h in (6, 4, 2):
        run(db, "flaky", h, success=False, error="HTTP 500: boom")
    run(db, "dead", 72, jobs=30)
    run(db, "dead", 1, success=False, error="timeout")
    run(db, "boardco", 1, jobs=3)
    run(db, "off", 500, jobs=1)
    db.add(ScraperConfigDB(company_slug="off", is_enabled=False))
    db.commit()


def test_board_health_records(db, history):
    report = scraper_health.health_report(db, now=NOW)
    assert report["boards"] == 5  # 'off' is disabled
    stale = {r["slug"] for r in report["stale"]}
    failing = {r["slug"] for r in report["failing"]}
    assert stale == {"dead", "never"} and failing == {"flaky"}

    records = {r["slug"]: r for r in scraper_health.board_health(
        db, scraper_health.enabled_boards(db), now=NOW)}
    fresh = records["fresh"]
    assert (fresh["jobs_found_last"], fresh["jobs_found_previous"], fresh["consecutive_failures"]) == (10, 12, 0)
    flaky = records["flaky"]
    assert flaky["consecutive_failures"] == 3 and flaky["last_error"] == "HTTP 500: boom" and not flaky["stale"]
    assert records["dead"]["consecutive_failures"] == 1 and records["never"]["last_run_at"] is None
    assert records["boardco"]["company_name"] == "Board Co"

    assert report["by_ats"] == {
        "ashby": {"boards": 1, "stale": 0, "failing": 0},
        "greenhouse": {"boards": 1, "stale": 0, "failing": 0},
        "lever": {"boards": 1, "stale": 0, "failing": 1},
        "other": {"boards": 1, "stale": 1, "failing": 0},
        "workday": {"boards": 1, "stale": 1, "failing": 0},
    }


def _user(db, role):
    user = User(email=f"{role}-health@example.com", name=role, role=role, is_active=True,
                password_hash=hash_password("Test-password-123"))
    db.add(user)
    db.commit()
    token, _ = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


def test_health_endpoint_is_admin_only(client, db, history):
    assert client.get("/api/scrapers/health", headers=_user(db, "user")).status_code in (401, 403)
    body = client.get("/api/scrapers/health", headers=_user(db, "admin")).json()
    assert {"boards", "stale", "failing", "by_ats", "checked_at"} <= set(body)
    assert {r["slug"] for r in body["failing"]} == {"flaky"}


def test_alert_lists_the_boards_that_broke(db, history, monkeypatch):
    from tasks import maintenance_tasks
    sent = []
    monkeypatch.setattr(maintenance_tasks, "get_db", lambda: Session(bind=db.get_bind()))
    monkeypatch.setattr(maintenance_tasks, "_send_alert_email", lambda to, subject, body: sent.append((subject, body)))
    monkeypatch.setattr(maintenance_tasks, "datetime", SimpleNamespace(utcnow=lambda: NOW))
    run(db, "fresh", 0, jobs=10)
    db.commit()
    report = maintenance_tasks.check_scraper_health_and_notify()
    assert report["failing"] == ["flaky"] and sorted(report["stale"]) == ["dead", "never"]
    (subject, body), = sent
    assert "3 of 5 boards broken" in subject
    assert "flaky (lever): 3 failed runs in a row: HTTP 500: boom" in body
    assert "dead (workday): no success since" in body and "never (other): never succeeded" in body
    assert "fresh" not in body.split("By ATS")[0]


def test_alert_ok_when_every_board_is_fresh(db, registry, monkeypatch):
    from tasks import maintenance_tasks
    monkeypatch.setattr(ScraperRegistry, "list_slugs", classmethod(lambda cls: ["fresh"]))
    monkeypatch.setattr(ScraperRegistry, "list_board_slugs", classmethod(lambda cls: []))
    db.add(ScraperRun(company_slug="fresh", success=True, jobs_found=4, jobs_new=2, run_at=datetime.utcnow()))
    db.commit()
    sent = []
    monkeypatch.setattr(maintenance_tasks, "get_db", lambda: Session(bind=db.get_bind()))
    monkeypatch.setattr(maintenance_tasks, "_send_alert_email", lambda to, subject, body: sent.append(subject))
    assert maintenance_tasks.check_scraper_health_and_notify()["is_healthy"] is True
    assert sent == ["[OK] Cariara Scraper Healthy — 1 board fresh, 2 new jobs"]
