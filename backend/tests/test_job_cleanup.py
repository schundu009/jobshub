"""
Admin › Settings › Data (services/job_cleanup.py, routes/analytics.py,
routes/ingest.py): old jobs and duplicates are deleted only when nobody used
them, open postings stay unless asked, and the description count uses the
backfill's own rules.
"""
from datetime import datetime, timedelta

import pytest

from models import Application, Company, Job, Note
from services import job_cleanup, job_descriptions
from tests.test_admin_and_scraping_fixes import headers, make_user

NOW = datetime(2026, 10, 6, 12, 0, 0)
LONG = "Build and run the payments platform. " * 20  # > 200 chars once normalized


@pytest.fixture
def company(db):
    c = Company(name="Acme")
    db.add(c)
    db.commit()
    return c


def add_job(db, company, title="Engineer", days_old=30, seen_days_ago=10, active=True, user_id=None,
            url=None, location="Remote", description=LONG, now=NOW):
    listed = now - timedelta(days=days_old)
    j = Job(title=title, company_id=company.id, location=location,
            job_url=url or f"https://x/{title}/{days_old}/{seen_days_ago}/{user_id}/{location}",
            job_description=description, is_active=active, user_id=user_id, source="acme",
            posted_date=listed, effective_posted_at=listed, first_seen_at=listed,
            last_seen_at=now - timedelta(days=seen_days_ago), created_at=listed)
    db.add(j)
    db.commit()
    return j


def test_old_jobs_keeps_open_used_and_user_added(db, company):
    owner = make_user(db, "o@example.com")
    stale = add_job(db, company, "Stale", days_old=30, seen_days_ago=10)
    closed = add_job(db, company, "Closed", days_old=30, seen_days_ago=0, active=False)
    add_job(db, company, "Open", days_old=30, seen_days_ago=0)
    applied = add_job(db, company, "Applied", days_old=30, seen_days_ago=10)
    noted = add_job(db, company, "Noted", days_old=30, seen_days_ago=10)
    add_job(db, company, "Mine", days_old=30, seen_days_ago=10, user_id=owner.id)
    add_job(db, company, "Fresh", days_old=2, seen_days_ago=10)
    db.add(Application(user_id=owner.id, job_id=applied.id, status="applied"))
    db.add(Note(job_id=noted.id, content="call recruiter"))
    db.commit()

    preview = job_cleanup.old_jobs(db, 7, now=NOW)
    assert preview["jobs_count"] == 2  # stale + closed
    assert (preview["kept_still_open"], preview["kept_with_user_activity"], preview["kept_user_added"]) == (1, 2, 1)
    assert db.query(Job).count() == 7  # a preview deletes nothing

    stale_id, closed_id = stale.id, closed.id
    done = job_cleanup.old_jobs(db, 7, apply=True, now=NOW)
    assert done["deleted"] == 2
    ids = {j.id for j in db.query(Job).all()}
    assert stale_id not in ids and closed_id not in ids
    assert {j.title for j in db.query(Job).all()} == {"Open", "Applied", "Noted", "Mine", "Fresh"}

    with_open = job_cleanup.old_jobs(db, 7, include_open=True, apply=True, now=NOW)
    assert with_open["deleted"] == 1 and with_open["still_open_included"] == 1
    assert {j.title for j in db.query(Job).all()} == {"Applied", "Noted", "Mine", "Fresh"}
    assert db.query(Application).count() == 1 and db.query(Note).count() == 1


def test_duplicates_same_url_keeps_the_used_or_open_copy(db, company):
    u = make_user(db, "d@example.com")
    url = "https://jobs.acme/123"
    old_closed = add_job(db, company, "A", url=url, active=False, seen_days_ago=40)
    open_copy = add_job(db, company, "A", url=url, seen_days_ago=0)
    used = add_job(db, company, "A2", url="https://jobs.acme/9")
    dup_of_used = add_job(db, company, "A2", url="https://jobs.acme/9", seen_days_ago=0)
    db.add(Application(user_id=u.id, job_id=used.id, status="applied"))
    db.commit()
    keep = {open_copy.id, used.id}
    drop = {old_closed.id, dup_of_used.id}

    res = job_cleanup.duplicates(db, apply=True, now=NOW)
    assert res["by_url"] == 2 and res["deleted"] == 2
    ids = {j.id for j in db.query(Job).all()}
    assert keep <= ids and not (drop & ids)  # the open copy, and the one someone applied to


def test_same_title_is_a_duplicate_only_with_the_same_description(db, company):
    a = add_job(db, company, "Software Engineer", url="https://jobs.acme/1", description=LONG)
    b = add_job(db, company, "Software Engineer", url="https://jobs.acme/2", description="  " + LONG.upper() + " ")
    c = add_job(db, company, "Software Engineer", url="https://jobs.acme/3", description="A different team. " * 20)
    d = add_job(db, company, "Software Engineer", url="https://jobs.acme/4", description="short")
    e = add_job(db, company, "Software Engineer", url="https://jobs.acme/5", description="short")
    pair, others = {a.id, b.id}, {c.id, d.id, e.id}

    res = job_cleanup.duplicates(db, apply=True, now=NOW)
    assert res["by_title_and_description"] == 1 and res["deleted"] == 1
    ids = {j.id for j in db.query(Job).all()}
    assert len(pair & ids) == 1  # one of the identical postings
    assert others <= ids  # another opening, and thin text proves nothing


def test_user_added_jobs_are_never_duplicates(db, company):
    u = make_user(db, "m@example.com")
    add_job(db, company, "Mine", url="https://jobs.acme/7", user_id=u.id)
    add_job(db, company, "Mine", url="https://jobs.acme/7", user_id=u.id)
    assert job_cleanup.duplicates(db, now=NOW)["duplicates_count"] == 0


def test_missing_descriptions_counts_match_the_backfill(db, company):
    now = datetime.utcnow()
    add_job(db, company, "Has text", seen_days_ago=0, now=now)
    add_job(db, company, "Empty", description=None, seen_days_ago=0, now=now)
    add_job(db, company, "Thin", description="Short summary.", seen_days_ago=0, now=now)
    retry = add_job(db, company, "Retry", description="", seen_days_ago=0, now=now)
    retry.description_fetch_attempted_at = now - timedelta(hours=1)
    retry.description_fetch_failures = 1
    gone = add_job(db, company, "Gone", description="", seen_days_ago=0, now=now)
    gone.description_fetch_failures = job_descriptions.MAX_FAILURES
    add_job(db, company, "Inactive", description="", active=False, now=now)
    db.commit()

    assert job_descriptions.missing_counts(db, now) == {"missing": 4, "ready": 2, "retrying_later": 1, "given_up": 1}
    ready = {j.title for j in db.query(Job).filter(job_descriptions.missing_filter(),
                                                    job_descriptions.ready_filter(now)).all()}
    assert ready == {"Empty", "Thin"}


def test_routes(client, db, company, monkeypatch):
    admin = make_user(db, "admin@example.com", role="admin")
    add_job(db, company, "Stale", days_old=400, seen_days_ago=400, now=datetime.utcnow())
    body = client.delete("/api/analytics/cleanup/old-jobs?days=7&dry_run=true", headers=headers(admin)).json()
    assert body["jobs_count"] == 1 and body["dry_run"] is True and "kept_still_open" in body
    assert client.delete("/api/analytics/cleanup/duplicates?dry_run=true",
                         headers=headers(admin)).json()["duplicates_count"] == 0

    add_job(db, company, "Empty", description=None, seen_days_ago=0, now=datetime.utcnow())
    assert client.get("/api/ingest/missing-descriptions", headers=headers(admin)).json()["ready"] == 1
    from tasks import maintenance_tasks
    queued = []
    monkeypatch.setattr(maintenance_tasks.fetch_missing_descriptions, "apply_async",
                        lambda *a, **k: queued.append(1) or type("T", (), {"id": "t1"})())
    res = client.post("/api/ingest/fetch-all-descriptions", headers=headers(admin)).json()
    assert res["jobs_queued"] == 1 and res["task_id"] == "t1" and queued == [1]

    member = make_user(db, "member@example.com")
    assert client.get("/api/ingest/missing-descriptions", headers=headers(member)).status_code == 403
