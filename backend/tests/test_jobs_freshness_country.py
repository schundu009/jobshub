"""/api/jobs freshness + country visibility, migration, backfill, contract-row move, Auto Apply, orchestration."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, inspect, text

from contracts.models import ContractJob
from models import Company, Job, User
from utils.security import create_access_token

NOW = datetime.utcnow()


def headers(user):
    token, _ = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


def add_job(db, ext, **kw):
    fields = dict(title=f"Engineer {ext}", location="Austin, TX", source="bigco", external_job_id=str(ext),
                  is_active=True, status="wishlist", posted_date=NOW - timedelta(days=2),
                  first_seen_at=NOW - timedelta(days=2), effective_posted_at=NOW - timedelta(days=2),
                  country_codes=",US,", is_evergreen=False)
    fields.update(kw)
    job = Job(**fields)
    db.add(job)
    db.commit()
    return job


def titles(resp):
    assert resp.status_code == 200, resp.text
    return sorted(j["title"] for j in resp.json()["jobs"])


@pytest.fixture
def jobs(db):
    add_job(db, 1, title="US job")
    add_job(db, 2, title="UK job", location="London, UK", country_codes=",GB,")
    add_job(db, 3, title="Unknown job", location="Remote", country_codes=None)
    add_job(db, 4, title="Evergreen job", is_evergreen=True, evergreen_reason="talent_pool")
    add_job(db, 5, title="Contract job", employment_type="contract")
    add_job(db, 6, title="Old listing", posted_date=NOW, first_seen_at=NOW - timedelta(days=20),
            effective_posted_at=NOW - timedelta(days=20))


def test_default_hides_evergreen_contract_and_foreign(client, jobs):
    assert titles(client.get("/api/jobs?all=true")) == ["Old listing", "US job", "Unknown job"]
    assert titles(client.get("/api/jobs?all=true&include_evergreen=true")) == [
        "Evergreen job", "Old listing", "US job", "Unknown job"]


def test_country_param_and_confirmed_only(client, jobs):
    assert titles(client.get("/api/jobs?all=true&country=GB")) == ["UK job", "Unknown job"]
    assert titles(client.get("/api/jobs?all=true&country=gb&confirmed_only=true")) == ["UK job"]
    assert titles(client.get("/api/jobs?all=true&country=ALL")) == ["Old listing", "UK job", "US job", "Unknown job"]
    assert client.get("/api/jobs?all=true&country=XX").status_code == 400


def test_user_country_and_admin_default(client, db, jobs, users):
    user = users[0]
    user.country, user.country_code = "United Kingdom", "GB"
    db.commit()
    assert titles(client.get("/api/jobs?all=true", headers=headers(user))) == ["UK job", "Unknown job"]
    # their own (private) jobs are always visible
    add_job(db, 7, title="My job", location="Paris", country_codes=",FR,", user_id=user.id)
    assert "My job" in titles(client.get("/api/jobs?all=true", headers=headers(user)))
    user.role = "admin"
    db.commit()
    # admins: every country + evergreen (contract roles never: they live in /api/contracts)
    assert len(titles(client.get("/api/jobs?all=true", headers=headers(user)))) == 6


def test_listed_fields_and_effective_time_filter(client, jobs):
    body = client.get("/api/jobs?all=true").json()["jobs"]
    old = next(j for j in body if j["title"] == "Old listing")
    assert old["listed_days"] == 20 and old["listed_since"].endswith("Z")
    assert old["country_codes"] == ["US"] and old["is_evergreen"] is False and "employment_type" in old
    # re-dated to today, but first seen 20 days ago: not "posted in the last week"
    assert titles(client.get("/api/jobs?all=true&posted_within_hours=168")) == ["US job", "Unknown job"]
    # default order: listed_since desc
    assert [j["title"] for j in body][-1] == "Old listing"


def test_countries_endpoint(client, jobs):
    body = client.get("/api/jobs/countries").json()
    assert body["countries"][0] == {"code": "US", "count": 2} and {"code": "GB", "count": 1} in body["countries"]
    assert body["unknown"] == 1


def test_detail_has_freshness(client, db, jobs, users):
    job = db.query(Job).filter(Job.title == "Old listing").one()
    body = client.get(f"/api/jobs/{job.id}", headers=headers(users[0])).json()
    assert body["listed_days"] == 20 and body["reposted_count"] == 0 and body["country_codes"] == ["US"]


def test_settings_country_is_normalized(client, db, users):
    r = client.put("/api/users/settings", json={"country": "United States"}, headers=headers(users[0]))
    assert r.status_code == 200, r.text
    db.refresh(users[0])
    assert users[0].country == "United States" and users[0].country_code == "US"


def test_analytics_summary_counts_contract_jobs(client, db, users):
    users[0].role = "admin"
    db.add(ContractJob(source="agency", external_job_id="1", title="Dev", is_active=True, employment_type="contract"))
    db.commit()
    body = client.get("/api/analytics/summary", headers=headers(users[0])).json()
    assert body["contract_jobs_active"] == 1


# ------------------------------------------------------------------ migration

def test_migration_is_idempotent(tmp_path):
    from migrations.job_classification import migrate_job_classification
    engine = create_engine(f"sqlite:///{tmp_path / 'old.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE jobs (id INTEGER PRIMARY KEY, title VARCHAR(500), posted_date DATETIME, "
                          "created_at DATETIME, date_found DATE, is_active BOOLEAN)"))
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, country VARCHAR(50))"))
        conn.execute(text("INSERT INTO jobs VALUES (1, 'a', '2026-01-10 00:00:00', '2026-01-05 00:00:00', NULL, 1)"))
        conn.execute(text("INSERT INTO users VALUES (1, 'United States'), (2, 'Narnia')"))
    for _ in range(2):
        with engine.begin() as conn:
            migrate_job_classification(conn)
    cols = {c["name"] for c in inspect(engine).get_columns("jobs")}
    assert {"employment_type", "first_seen_at", "last_seen_at", "reposted_count", "is_evergreen",
            "evergreen_reason", "effective_posted_at", "country_codes"} <= cols
    idx = {i["name"] for i in inspect(engine).get_indexes("jobs")}
    assert {"ix_jobs_employment_type", "ix_jobs_active_effective_posted", "ix_jobs_country_codes"} <= idx
    with engine.connect() as conn:
        first_seen, eff, reposted, ever = conn.execute(text(
            "SELECT first_seen_at, effective_posted_at, reposted_count, is_evergreen FROM jobs")).one()
        assert str(first_seen).startswith("2026-01-05") and str(eff).startswith("2026-01-05")
        assert reposted == 0 and ever == 0
        assert conn.execute(text("SELECT country_code FROM users ORDER BY id")).fetchall() == [("US",), (None,)]
    engine.dispose()


# ------------------------------------------------------------------ backfill + move

def test_backfill_dry_run_then_apply(db):
    co = Company(name="BigCo")
    db.add(co)
    db.commit()
    db.add_all([
        Job(title="Engineer", location="Bangalore", company_id=co.id, is_active=True, created_at=NOW - timedelta(days=3)),
        Job(title="Java Developer (Contract)", location="Austin, TX", company_id=co.id, is_active=True,
            created_at=NOW - timedelta(days=3)),
        Job(title="Join our Talent Community", location="Remote", company_id=co.id, is_active=True,
            created_at=NOW - timedelta(days=3)),
    ])
    db.commit()
    from scripts.backfill_job_classification import main
    lines = []
    summary = main([], db=db)  # dry run
    assert summary["mode"] == "dry-run" and summary["jobs"]["changed"] == 3
    assert db.query(Job).filter(Job.country_codes.isnot(None)).count() == 0  # nothing written
    assert summary["jobs"]["top_countries"] == [("IN", 1)] and summary["jobs"]["top_unknown_locations"] == [("Remote", 1)]

    summary = main(["--apply"], db=db)
    rows = {j.title: j for j in db.query(Job)}
    assert rows["Engineer"].country_codes == ",IN," and rows["Engineer"].first_seen_at is not None
    assert rows["Java Developer (Contract)"].employment_type == "contract"
    assert rows["Join our Talent Community"].is_evergreen and rows["Join our Talent Community"].evergreen_reason == "talent_pool"
    assert main(["--apply"], db=db)["jobs"]["changed"] == 0  # idempotent


def test_migrate_contract_rows(db):
    co = Company(name="BigCo")
    db.add(co)
    db.commit()
    db.add_all([
        Job(title="Java Developer (Contract)", location="Austin, TX", company_id=co.id, source="bigco",
            external_job_id="c1", is_active=True, posted_date=NOW - timedelta(days=3), job_description="$70/hr W2"),
        Job(title="Staff Engineer", location="Austin, TX", company_id=co.id, source="bigco", external_job_id="f1",
            is_active=True),
    ])
    db.commit()
    co_id = co.id
    from contracts.scripts.migrate_contract_rows import main
    dry = main([], db=db)
    assert dry["contract_rows"] == 1 and db.query(ContractJob).count() == 0
    assert db.query(Job).filter(Job.is_active == True).count() == 2  # noqa: E712
    done = main(["--apply"], db=db)
    assert done["moved"] == 1 and done["deactivated"] == 1
    c = db.query(ContractJob).one()
    assert (c.source, c.source_type, c.company_id, c.pay_rate_min) == ("bigco", "company_board", co_id, 70.0)
    assert db.query(Job).filter(Job.external_job_id == "c1").one().is_active is False


# ------------------------------------------------------------------ Auto Apply + orchestration

def test_auto_apply_candidates_skip_stale_evergreen_and_foreign(db):
    from services.apply.matching import candidate_jobs, is_stale_for_apply
    add_job(db, 1, title="Fresh US")
    add_job(db, 2, title="Evergreen", is_evergreen=True)
    add_job(db, 3, title="Listed 50d", posted_date=NOW - timedelta(days=1), effective_posted_at=NOW - timedelta(days=50))
    add_job(db, 4, title="India", location="Pune", country_codes=",IN,")
    add_job(db, 5, title="Unknown", location="Remote", country_codes=None)
    got = sorted(j.title for j in candidate_jobs(db, country="US"))
    assert got == ["Fresh US", "Unknown"]
    assert sorted(j.title for j in candidate_jobs(db, country="IN")) == ["India", "Unknown"]
    assert is_stale_for_apply(db.query(Job).filter(Job.title == "Listed 50d").one())


def test_full_time_orchestrator_skips_staffing(monkeypatch):
    from tasks import scraper_tasks
    from scrapers.base import ScraperType

    class Cfg:
        scraper_type = ScraperType.HTTP

    class S:
        config = Cfg()

    meta = {"bigco": {"category": "custom"}, "agency": {"category": "staffing"}}
    monkeypatch.setattr(scraper_tasks, "_interval_gate", lambda force: None)
    monkeypatch.setattr(scraper_tasks.ScraperRegistry, "get_all", classmethod(lambda cls: {"bigco": S, "agency": S}))
    monkeypatch.setattr(scraper_tasks.ScraperRegistry, "get_metadata", classmethod(lambda cls, s: meta.get(s)))
    monkeypatch.setattr(scraper_tasks, "is_scraper_enabled", lambda db, slug: True)
    dispatched = []
    monkeypatch.setattr(scraper_tasks, "_dispatch_staggered", lambda sigs, queue: dispatched.extend(sigs))
    monkeypatch.setattr(scraper_tasks, "get_db", lambda: type("D", (), {"expire_all": lambda s: None, "close": lambda s: None})())
    scraper_tasks.scrape_all_companies(force=True)
    assert [s.args[0] for s in dispatched] == ["bigco"]


def test_contract_celery_wiring():
    import celery_app
    conf = celery_app.celery_app.conf
    assert "contracts.tasks" in conf.include
    assert any(q.name == "contracts" for q in conf.task_queues)
    beat = {v["task"] for v in conf.beat_schedule.values()}
    assert {"contracts.tasks.scrape_all_contracts", "contracts.tasks.expire_contract_jobs"} <= beat
