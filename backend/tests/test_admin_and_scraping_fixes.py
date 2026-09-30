"""Admin-only enforcement, scraper run/record fixes, settings models, schedules,
company normalization and the one-off maintenance scripts."""
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session

from models import AppSetting, Company, Job, Note, ScraperConfigDB, ScraperRun, User
from routes import scrapers as scraper_routes
from scrapers.base import ScrapedJob, ScrapeResult, ScraperType
from services import scraper_service
from services.company_resolver import CompanyResolver, normalize_company_key
from utils.security import create_access_token, hash_password


def headers(user):
    token, _ = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


def make_user(db, email, role="user"):
    user = User(email=email, name=email.split("@")[0], role=role, is_active=True,
                password_hash=hash_password("Test-password-123"))
    db.add(user)
    db.commit()
    return user


@pytest.fixture
def admin(db):
    return make_user(db, "admin@example.com", role="admin")


@pytest.fixture
def member(db):
    return make_user(db, "member@example.com", role="user")


def session_factory(db):
    """Fresh sessions on the test engine, for task code that opens its own."""
    return lambda: Session(bind=db.get_bind())


# ---------------------------------------------------------------- C2 admin-only

ADMIN_GETS = [
    "/api/scrapers/status",
    "/api/scrapers/",
    "/api/settings/ai-model",
    "/api/settings/api-key",
    "/api/settings/default-ai-provider",
    "/api/celery/tasks/recent",
    "/api/celery/schedules",
    "/api/ingest/sources",
    "/api/analytics/summary",
]


@pytest.mark.parametrize("path", ADMIN_GETS)
def test_admin_endpoints_reject_non_admin(client, member, path):
    assert client.get(path).status_code == 401
    assert client.get(path, headers=headers(member)).status_code == 403


@pytest.mark.parametrize("path", ADMIN_GETS)
def test_admin_endpoints_allow_admin(client, admin, path, monkeypatch):
    monkeypatch.setattr(scraper_routes.ScraperRegistry, "list_slugs", classmethod(lambda cls: []))
    monkeypatch.setattr(scraper_routes.ScraperRegistry, "get_disabled", classmethod(lambda cls: {}))
    assert client.get(path, headers=headers(admin)).status_code == 200


@pytest.mark.parametrize("role", ["administrator", "manager", "developer"])
def test_all_admin_roles_accepted(client, db, role):
    user = make_user(db, f"{role}@example.com", role=role)
    assert client.get("/api/settings/ai-model", headers=headers(user)).status_code == 200


@pytest.mark.parametrize("method,path", [
    ("post", "/api/scrapers/run-all"),
    ("post", "/api/scrapers/run-warning"),
    ("post", "/api/scrapers/acme/run-sync"),
    ("post", "/api/scrapers/maintenance/reset-failures"),
    ("post", "/api/scrapers/acme/enable"),
    ("delete", "/api/scrapers/custom/acme"),
    ("post", "/api/celery/tasks/trigger/scrape_all_companies"),
    ("post", "/api/celery/workers/purge/default"),
    ("put", "/api/celery/schedules"),
    ("post", "/api/ingest/refresh"),
    ("delete", "/api/settings/api-key"),
])
def test_mutations_forbidden_for_non_admin(client, member, method, path):
    kwargs = {"json": {}} if method in ("post", "put") else {}
    response = getattr(client, method)(path, headers=headers(member), **kwargs)
    assert response.status_code == 403


def test_refetch_description_stays_available_to_users_for_visible_jobs(client, db, member, users, monkeypatch):
    from services import ingestion_service
    other = users[0]
    shared = Job(title="Shared", job_url="https://example.com/a")
    private = Job(title="Theirs", job_url="https://example.com/b", user_id=other.id)
    db.add_all([shared, private])
    db.commit()
    monkeypatch.setattr(ingestion_service, "fetch_job_description_from_url", lambda url: "x" * 200)
    ok = client.post(f"/api/ingest/refetch-description/{shared.id}", headers=headers(member))
    assert ok.status_code == 200 and ok.json()["new_description_length"] == 200
    hidden = client.post(f"/api/ingest/refetch-description/{private.id}", headers=headers(member))
    assert hidden.status_code == 404


# ------------------------------------------------------------ P4 jobs/companies

def test_shared_job_edit_is_admin_only_and_keeps_it_shared(client, db, admin, member):
    job = Job(title="Scraped", source="acme")
    mine = Job(title="Mine", user_id=member.id)
    db.add_all([job, mine])
    db.commit()

    assert client.put(f"/api/jobs/{job.id}", json={"title": "x"}, headers=headers(member)).status_code == 403
    assert client.delete(f"/api/jobs/{job.id}", headers=headers(member)).status_code == 403
    assert client.put(f"/api/jobs/{job.id}", json={"title": "Fixed"}, headers=headers(admin)).status_code == 200
    db.refresh(job)
    assert job.title == "Fixed" and job.user_id is None  # admin edit doesn't take ownership

    assert client.put(f"/api/jobs/{mine.id}", json={"title": "Mine 2"}, headers=headers(member)).status_code == 200
    assert client.delete(f"/api/jobs/{mine.id}", headers=headers(member)).status_code == 200
    assert client.delete(f"/api/jobs/{job.id}", headers=headers(admin)).status_code == 200


def test_shared_company_edit_and_delete_rules(client, db, admin, member):
    shared = Company(name="Shared Co")
    busy = Company(name="Busy Co")
    db.add_all([shared, busy])
    db.flush()
    db.add(Job(title="x", company_id=busy.id))
    db.commit()

    assert client.put(f"/api/companies/{shared.id}", json={"notes": "n"}, headers=headers(member)).status_code == 403
    assert client.delete(f"/api/companies/{shared.id}", headers=headers(member)).status_code == 403
    assert client.put(f"/api/companies/{shared.id}", json={"notes": "n"}, headers=headers(admin)).status_code == 200
    db.refresh(shared)
    assert shared.user_id is None
    assert client.delete(f"/api/companies/{busy.id}", headers=headers(admin)).status_code == 409
    assert client.delete(f"/api/companies/{shared.id}", headers=headers(admin)).status_code == 200


# ---------------------------------------------------------------- C10 / C11

def test_health_db_hides_connection_details(client):
    body = client.get("/health/db").json()
    assert set(body) == {"status", "latency_ms"}


def test_metrics_requires_admin_or_token(client, admin, member, monkeypatch):
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers=headers(member)).status_code == 403
    assert client.get("/metrics", headers=headers(admin)).status_code == 200
    monkeypatch.setenv("METRICS_TOKEN", "t0ken")
    assert client.get("/metrics", headers={"X-Metrics-Token": "t0ken"}).status_code == 200
    assert client.get("/metrics", headers={"X-Metrics-Token": "nope"}).status_code == 401


@pytest.mark.parametrize("path,env", [
    ("/api/scrapers/webhook/trigger", "SCRAPER_WEBHOOK_SECRET"),
    ("/api/scrapers/webhook/run-sync", "SCRAPER_WEBHOOK_SECRET"),
    ("/api/apify/webhook/trigger", "APIFY_WEBHOOK_SECRET"),
    ("/api/apify/webhook/bulk-scrape", "APIFY_WEBHOOK_SECRET"),
])
def test_webhooks_disabled_without_secret(client, monkeypatch, path, env):
    monkeypatch.delenv(env, raising=False)
    for old_default in ("cariara-scrape-2024", "apify-cariara-2024"):
        response = client.post(f"{path}?secret={old_default}")
        assert response.status_code == 503 and response.json()["detail"] == "webhook disabled"
    monkeypatch.setenv(env, "s3cret")
    assert client.post(f"{path}?secret=wrong").status_code == 403


# ---------------------------------------------------------------- S1 / S3

class FakeHTTPScraper:
    config = SimpleNamespace(scraper_type=ScraperType.HTTP, company_slug="acme",
                             company_name="Acme", allow_empty=False)
    outcome = "jobs"

    def __init__(self, rate_limiter=None, browser_pool=None):
        pass

    async def run(self):
        if self.outcome == "raise":
            raise RuntimeError("board exploded")
        now = datetime.utcnow()
        jobs = [ScrapedJob(title="SRE", location="Remote", job_url="https://acme/1", external_job_id="1", posted_date=now)]
        return ScrapeResult(success=True, jobs=jobs, started_at=now, completed_at=now)


class FakeBrowserScraper(FakeHTTPScraper):
    config = SimpleNamespace(scraper_type=ScraperType.PLAYWRIGHT, company_slug="acmepw",
                             company_name="Acme PW", allow_empty=False)


@pytest.fixture
def fake_registry(monkeypatch):
    classes = {"acme": FakeHTTPScraper, "acmepw": FakeBrowserScraper}
    meta = {"acme": {"company_name": "Acme", "careers_url": "https://acme"},
            "acmepw": {"company_name": "Acme PW", "careers_url": "https://acmepw"}}
    registry = scraper_routes.ScraperRegistry
    monkeypatch.setattr(registry, "get", classmethod(lambda cls, s: classes.get(s)))
    monkeypatch.setattr(registry, "get_metadata", classmethod(lambda cls, s: meta.get(s)))
    monkeypatch.setattr(registry, "list_slugs", classmethod(lambda cls: list(classes)))
    monkeypatch.setattr(registry, "get_disabled", classmethod(lambda cls: {}))
    dispatched = []
    monkeypatch.setattr(scraper_routes, "_dispatch_scrape",
                        lambda slug: dispatched.append(slug) or SimpleNamespace(id=f"task-{slug}"))
    FakeHTTPScraper.outcome = "jobs"
    return dispatched


def test_run_sync_http_saves_and_records(client, db, admin, fake_registry):
    response = client.post("/api/scrapers/acme/run-sync", headers=headers(admin))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success" and body["jobs_found"] == 1 and body["jobs_new"] == 1
    assert db.query(Job).filter(Job.source == "acme").count() == 1
    assert db.query(ScraperRun).filter_by(company_slug="acme", success=True).count() == 1


def test_run_sync_browser_is_queued(client, admin, fake_registry):
    body = client.post("/api/scrapers/acmepw/run-sync", headers=headers(admin)).json()
    assert body["status"] == "queued" and body["task_id"] == "task-acmepw"
    assert fake_registry == ["acmepw"]


def test_run_sync_failure_is_reported_not_500(client, admin, fake_registry):
    FakeHTTPScraper.outcome = "raise"
    response = client.post("/api/scrapers/acme/run-sync", headers=headers(admin))
    assert response.status_code == 200
    assert response.json()["status"] == "failed" and "board exploded" in response.json()["error"]


def test_run_warning_returns_message_and_count(client, db, admin, fake_registry):
    db.add(ScraperConfigDB(company_slug="acme", consecutive_failures=3))
    db.add(ScraperConfigDB(company_slug="acmepw", consecutive_failures=0,
                           last_success_at=datetime.utcnow(), total_runs=1))
    db.commit()
    body = client.post("/api/scrapers/run-warning", headers=headers(admin)).json()
    assert body["status"] == "queued" and body["count"] == 1 and body["queued"] == 1
    assert "Queued 1" in body["message"]
    body = client.post("/api/scrapers/run-warning-sync", headers=headers(admin)).json()
    assert body["status"] == "queued" and body["count"] == 1


def test_status_lists_code_disabled_scrapers(client, admin, fake_registry, monkeypatch):
    monkeypatch.setattr(scraper_routes.ScraperRegistry, "get_disabled", classmethod(
        lambda cls: {"oldco": {"company_name": "Old Co", "reason": "board dead"}}))
    body = client.get("/api/scrapers/status", headers=headers(admin)).json()
    old = [s for s in body if s["company_slug"] == "oldco"][0]
    assert old["is_enabled"] is False and old["disabled_reason"] == "board dead"
    assert all("has_scraper" in s for s in body)


def test_purge_rejects_undeclared_queue(client, admin):
    assert client.post("/api/celery/workers/purge/everything", headers=headers(admin)).status_code == 400


# ---------------------------------------------------------------- S5 settings

def test_ai_model_lists_come_from_services(client, db, admin):
    from services.anthropic_service import CLAUDE_MODELS
    from services.openai_service import OPENAI_MODELS

    body = client.get("/api/settings/ai-model", headers=headers(admin)).json()
    assert [m["id"] for m in body["claude_models"]] == list(CLAUDE_MODELS)
    assert [m["id"] for m in body["openai_models"]] == list(OPENAI_MODELS)
    assert body["claude_model"] == "claude-sonnet-5-5"

    saved = client.post("/api/settings/ai-model", json={"model": "claude-3-5-sonnet-20241022"},
                        headers=headers(admin)).json()
    assert saved["model"] == "claude-sonnet-5-5"
    assert db.query(AppSetting).filter_by(key="claude_model").one().value == "claude-sonnet-5-5"
    assert client.post("/api/settings/ai-model", json={"model": "gpt-99"},
                       headers=headers(admin)).status_code == 400


def test_anthropic_key_test_uses_current_model():
    from routes import settings as settings_routes
    assert settings_routes.TEST_CLAUDE_MODEL == "claude-haiku-4-5-20251001"


# ---------------------------------------------------------------- S6/S7 schedules

def test_schedules_get_is_structured_and_put_applies(client, db, admin):
    body = client.get("/api/celery/schedules", headers=headers(admin)).json()
    assert set(body["settings"]) == {"scraper_interval_hours", "auto_apply_enabled", "description_fetch_enabled"}
    names = {s["name"] for s in body["schedules"]}
    assert "scrape-all-companies" in names
    assert not any("application" in n for n in names)  # auto-apply beat entries removed

    update = {"scraper_interval_hours": 12, "auto_apply_enabled": False, "description_fetch_enabled": False}
    assert client.put("/api/celery/schedules", json=update, headers=headers(admin)).status_code == 200
    body = client.get("/api/celery/schedules", headers=headers(admin)).json()
    assert body["settings"] == update


def test_disabled_flags_short_circuit_tasks(db, monkeypatch):
    from tasks import maintenance_tasks
    db.add_all([AppSetting(key="description_fetch_enabled", value="false")])
    db.commit()
    monkeypatch.setattr(maintenance_tasks, "get_db", session_factory(db))
    assert maintenance_tasks.fetch_missing_descriptions.run()["status"] == "skipped"
    # The legacy server-side auto-apply processor is gone entirely.
    import importlib.util
    assert importlib.util.find_spec("tasks.auto_apply_tasks") is None


def test_scrape_all_respects_interval(db, monkeypatch):
    from tasks import scraper_tasks
    monkeypatch.setattr(scraper_tasks, "get_db", session_factory(db))
    db.add(AppSetting(key="scraper_interval_hours", value="6"))
    db.add(AppSetting(key="scraper_last_orchestrated_at",
                      value=(datetime.utcnow() - timedelta(hours=1)).isoformat()))
    db.commit()
    assert scraper_tasks._interval_gate(force=False)["skipped"] == "interval"
    assert scraper_tasks._interval_gate(force=True) is None  # manual run proceeds, records now
    db.expire_all()
    db.query(AppSetting).filter_by(key="scraper_last_orchestrated_at").one().value = (
        datetime.utcnow() - timedelta(hours=7)).isoformat()
    db.commit()
    assert scraper_tasks._interval_gate(force=False) is None


# ---------------------------------------------------------------- empty_result / timeouts

def test_empty_result_after_jobs_is_recorded_as_failure(db):
    from tasks.scraper_tasks import record_scraper_run
    now = datetime.utcnow()
    record_scraper_run(db, "zeroco", ScrapeResult(success=True, jobs_found=5, started_at=now, completed_at=now))
    record_scraper_run(db, "zeroco", ScrapeResult(success=True, jobs_found=0, started_at=now, completed_at=now))
    last = db.query(ScraperRun).filter_by(company_slug="zeroco").order_by(ScraperRun.id.desc()).first()
    assert last.success is False and last.error_type == "empty_result"
    cfg = db.query(ScraperConfigDB).filter_by(company_slug="zeroco").one()
    assert cfg.consecutive_failures == 1 and cfg.is_enabled is True

    # a board that never had jobs may legitimately be empty
    record_scraper_run(db, "newco", ScrapeResult(success=True, jobs_found=0, started_at=now, completed_at=now))
    assert db.query(ScraperRun).filter_by(company_slug="newco").one().success is True


def test_timeouts_are_recorded(db, monkeypatch):
    from scrapers.base import ScraperErrorType
    from tasks import scraper_tasks
    monkeypatch.setattr(scraper_tasks, "get_db", session_factory(db))
    scraper_tasks._record_failure("slowco", "soft time limit exceeded", ScraperErrorType.TIMEOUT, "t1")
    scraper_tasks._record_failure("slowco", "boom", "exception", "t2")
    runs = db.query(ScraperRun).filter_by(company_slug="slowco").order_by(ScraperRun.id).all()
    assert [r.error_type for r in runs] == ["timeout", "exception"]
    assert all(not r.success for r in runs)


# ---------------------------------------------------------------- companies

@pytest.mark.parametrize("a,b", [
    ("roblox", "Roblox"), ("Block", "Block (Square)"), ("T-Mobile USA, Inc.", "T-Mobile"),
    ("Apply.Careers.Microsoft.Com", "Microsoft"), ("Meta1", "Meta"),
    ("Paloaltonetworks", "Palo Alto Networks"), ("Scaleai", "Scale AI"), ("Togetherai", "Together AI"),
    ("Snap", "Snap Inc."), ("Dell", "Dell Technologies"), ("Expedia", "Expedia Group"),
    ("JPMorgan", "JPMorgan Chase"), ("Unity", "Unity Technologies"), ("amazon.com", "Amazon"),
])
def test_company_keys_unify_known_duplicates(a, b):
    assert normalize_company_key(a) == normalize_company_key(b)


def test_distinct_companies_stay_distinct():
    assert normalize_company_key("Snap") != normalize_company_key("Snowflake")
    assert normalize_company_key("Meta") != normalize_company_key("Metabase")


def test_save_scraped_jobs_reuses_normalized_company(db, monkeypatch):
    monkeypatch.setattr(scraper_service.ScraperRegistry, "get_metadata",
                        classmethod(lambda cls, s: {"company_name": "Snap Inc.", "careers_url": None}))
    existing = Company(name="snap")
    db.add_all([existing])
    db.commit()
    now = datetime.utcnow()
    scraper_service.save_scraped_jobs(db, "snap", [
        ScrapedJob(title="SWE", location="Remote", job_url="https://snap/1", external_job_id="1", posted_date=now)
    ])
    assert db.query(Company).count() == 1
    assert db.query(Job).one().company_id == existing.id
    assert CompanyResolver(db).find("Snap Inc.").id == existing.id


def _dup_fixture(db, users):
    owner = users[0]
    canonical = Company(name="Microsoft")
    dup = Company(name="Apply.Careers.Microsoft.Com")
    dup2 = Company(name="microsoft")
    private = Company(name="Microsoft", user_id=owner.id)
    other = Company(name="Stripe")
    db.add_all([canonical, dup, dup2, private, other])
    db.flush()
    twin_keep = Job(title="SWE", company_id=canonical.id, external_job_id="42")
    twin_user = Job(title="SWE", company_id=dup.id, external_job_id="42", user_id=owner.id, status="applied")
    moved = [Job(title=f"Job {i}", company_id=dup.id, external_job_id=f"d{i}") for i in range(3)]
    loose = Job(title="No id", company_id=dup2.id)
    db.add_all([twin_keep, twin_user, loose, *moved])
    db.flush()
    db.add(Note(job_id=twin_keep.id, content="on the canonical copy"))
    db.commit()
    return canonical, dup, dup2, private, other, twin_keep, twin_user


def test_merge_script_dry_run_and_apply(db, users):
    from scripts import merge_duplicate_companies as merge

    canonical, dup, dup2, private, other, twin_keep, twin_user = _dup_fixture(db, users)
    registry = {"microsoft": "Microsoft"}
    conn = db.connection()

    groups = merge.plan(conn, registry)
    assert len(groups) == 1
    group = groups[0]
    assert group.canonical_id == canonical.id and group.rename_to is None
    assert {d[0] for d in group.duplicates} == {dup.id, dup2.id}
    assert "merge" in merge.format_plan(groups)
    assert db.query(Company).count() == 5  # dry run changed nothing

    stats = merge.apply(conn, groups)
    db.commit()
    db.expire_all()
    assert stats["companies_deleted"] == 2 and stats["jobs_merged"] == 1
    assert {c.name for c in db.query(Company).all()} == {"Microsoft", "Stripe"}
    assert db.query(Company).filter(Company.user_id == users[0].id).count() == 1  # private untouched
    assert db.query(Job).filter(Job.company_id == canonical.id).count() == 5
    # the user's applied copy survives and inherits the canonical copy's note
    kept = db.query(Job).filter(Job.external_job_id == "42").one()
    assert kept.id == twin_user.id and kept.status == "applied"
    assert db.query(Note).one().job_id == kept.id

    assert merge.plan(db.connection(), registry) == []  # idempotent


def test_merge_script_renames_to_registry_name(db):
    from scripts import merge_duplicate_companies as merge
    db.add_all([Company(name="snap"), Company(name="SNAP INC")])
    db.commit()
    groups = merge.plan(db.connection(), {"snap": "Snap"})
    merge.apply(db.connection(), groups)
    db.commit()
    assert [c.name for c in db.query(Company).all()] == ["Snap"]


def test_companies_list_has_scraper_flag(client, db, users, monkeypatch):
    import routes.companies as company_routes
    monkeypatch.setattr(company_routes, "registry_company_keys", lambda: {"stripe": "stripe"})
    db.add_all([Company(name="Stripe, Inc."), Company(name="Corner Bakery")])
    db.commit()
    rows = {c["name"]: c for c in client.get("/api/companies", headers=headers(users[0])).json()}
    assert rows["Stripe, Inc."]["has_scraper"] is True
    assert rows["Corner Bakery"]["has_scraper"] is False


# ---------------------------------------------------------------- auto-heal / scripts

def test_auto_heal_skips_non_greenhouse_and_never_resets_without_fix(db, monkeypatch):
    from scrapers.custom.remaining_scrapers import AshbyMixin, GreenhouseMixin
    from scrapers.base import HTTPScraper
    from tasks import maintenance_tasks

    class GH(GreenhouseMixin, HTTPScraper):
        config = SimpleNamespace(company_slug="ghco", company_name="GH Co", scraper_type=ScraperType.HTTP)
        API_URL = "https://boards-api.greenhouse.io/v1/boards/ghco/jobs"

    class AB(AshbyMixin, HTTPScraper):
        config = SimpleNamespace(company_slug="abco", company_name="AB Co", scraper_type=ScraperType.HTTP)
        API_URL = "https://api.ashbyhq.com/posting-api/job-board/abco"

    classes = {"ghco": GH, "abco": AB}
    monkeypatch.setattr(maintenance_tasks, "get_db", session_factory(db))
    from scrapers.registry import ScraperRegistry
    monkeypatch.setattr(ScraperRegistry, "get", classmethod(lambda cls, s: classes.get(s)))
    probed = []

    def probe(ats, url):
        probed.append(url)
        return 12 if url.endswith("/ghcoinc/jobs") else 0

    monkeypatch.setattr(maintenance_tasks, "_probe_board", probe)
    db.add_all([ScraperConfigDB(company_slug="ghco", consecutive_failures=4),
                ScraperConfigDB(company_slug="abco", consecutive_failures=12)])
    db.commit()

    result = maintenance_tasks.auto_heal_scrapers.run()
    assert [h["slug"] for h in result["healed"]] == ["ghco"]
    assert all("greenhouse.io" in u for u in probed)  # never probed another ATS
    assert all("ghco" in u for u in probed)  # only variants of its own token
    db.expire_all()
    ab = db.query(ScraperConfigDB).filter_by(company_slug="abco").one()
    assert ab.is_enabled is True and ab.consecutive_failures == 12  # skipped entirely
    gh = db.query(ScraperConfigDB).filter_by(company_slug="ghco").one()
    assert gh.consecutive_failures == 0 and gh.config_overrides["url_override"].endswith("/ghcoinc/jobs")


def test_reenable_script(db):
    from scripts import reenable_repaired_scrapers as script
    from scrapers.custom.remaining_scrapers import AshbyMixin
    from scrapers.base import HTTPScraper

    class AB(AshbyMixin, HTTPScraper):
        config = SimpleNamespace(company_slug="abco", company_name="AB Co")

    registry = SimpleNamespace(
        list_slugs=lambda: ["abco"],
        get=lambda slug: AB,
        get_disabled=lambda: {"deadco": {"reason": "gone"}},
    )
    db.add(ScraperConfigDB(company_slug="abco", is_enabled=False, consecutive_failures=11,
                           config_overrides={"auto_disabled": True, "url_override": "https://boards-api.greenhouse.io/x"}))
    db.add_all([Job(title="a", source="deadco", is_active=True), Job(title="b", source="abco", is_active=True)])
    db.commit()

    dry = script.plan_and_apply(db, apply=False, registry=registry)
    assert dry["reenabled"][0]["slug"] == "abco" and dry["deactivated_jobs"] == {"deadco": 1}
    assert db.query(ScraperConfigDB).one().is_enabled is False

    script.plan_and_apply(db, apply=True, registry=registry)
    db.commit()
    cfg = db.query(ScraperConfigDB).one()
    assert cfg.is_enabled is True and cfg.consecutive_failures == 0 and not cfg.config_overrides
    assert db.query(Job).filter_by(source="deadco").one().is_active is False
    assert script.plan_and_apply(db, apply=False, registry=registry) == {"reenabled": [], "deactivated_jobs": {}}
