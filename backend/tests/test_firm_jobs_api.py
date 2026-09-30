"""GET /api/jobs filters + skills matching, /api/jobs/facets, public job detail, work_type column."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine, inspect, text

from models import Company, Job
from services import firm_matching as fm
from utils.security import create_access_token

NOW = datetime.utcnow()
BASE = "/api/jobs?country=US&include_evergreen=false"


def headers(user):
    token, _ = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


_seq = iter(range(1, 10_000))


def add_job(db, **kw):
    n = next(_seq)
    age = kw.pop("age_days", 2)
    when = NOW - timedelta(days=age, minutes=n)
    fields = dict(title=f"Engineer {n}", location="Austin, TX", source="greenhouse", external_job_id=str(n),
                  is_active=True, status="wishlist", posted_date=when, first_seen_at=when,
                  effective_posted_at=when, country_codes=",US,", is_evergreen=False)
    fields.update(kw)
    job = Job(**fields)
    db.add(job)
    db.commit()
    return job


def titles(resp):
    assert resp.status_code == 200, resp.text
    return sorted(j["title"] for j in resp.json()["jobs"])


@pytest.fixture
def companies(db):
    rows = {name: Company(name=name) for name in ("Stripe", "Google", "Acme Robotics")}
    db.add_all(rows.values())
    db.commit()
    return rows


# ---------------------------------------------------------------- applied_filters + q

def test_applied_filters_lists_only_the_filters_used(client, db):
    add_job(db, title="Backend Engineer")
    body = client.get(f"{BASE}&all=true").json()
    assert body["applied_filters"] == []
    body = client.get(f"{BASE}&all=true&q=backend&location=Austin&work_type=onsite,bogus&salary_min=1"
                      f"&company=Stripe&employment_type=full_time").json()
    assert body["applied_filters"] == ["q", "location", "work_type", "salary", "company", "employment_type"]
    # unknown values only: nothing to apply
    assert client.get(f"{BASE}&all=true&work_type=bogus&employment_type=nope").json()["applied_filters"] == []
    # legacy role scoring responses carry it too
    assert client.get(f"{BASE}&role=backend&min_score=0").json()["applied_filters"] == []


def test_q_all_words_across_fields(client, db, companies):
    add_job(db, title="Senior Backend Engineer", company_id=companies["Stripe"].id)
    add_job(db, title="Platform Engineer", department="Backend Infrastructure")
    add_job(db, title="Staff Engineer", ai_tech_stack=["Kubernetes", "Go"])
    add_job(db, title="Account Executive", company_id=companies["Stripe"].id)
    add_job(db, title="Designer", job_description="We use backend kubernetes everywhere")
    assert titles(client.get(f"{BASE}&all=true&q=BACKEND")) == ["Platform Engineer", "Senior Backend Engineer"]
    assert titles(client.get(f"{BASE}&all=true&q=stripe backend")) == ["Senior Backend Engineer"]
    assert titles(client.get(f"{BASE}&all=true&q=kubernetes")) == ["Staff Engineer"]
    # description only on request
    assert titles(client.get(f"{BASE}&all=true&q=kubernetes&q_description=true")) == ["Designer", "Staff Engineer"]


def test_q_short_tokens_match_whole_words(client, db, companies):
    add_job(db, title="Go Developer")
    add_job(db, title="Backend Engineer", ai_tech_stack=["go", "aws"])
    add_job(db, title="Django Developer")
    add_job(db, title="Engineer", company_id=companies["Google"].id)
    assert titles(client.get(f"{BASE}&all=true&q=go")) == ["Backend Engineer", "Go Developer"]
    assert titles(client.get(f"{BASE}&all=true&q=goo")) == []
    assert titles(client.get(f"{BASE}&all=true&q=goog")) == ["Engineer"]


# ---------------------------------------------------------------- location / work type

def test_location_metro_label_key_and_free_text(client, db):
    add_job(db, title="SF", location="San Francisco, CA")
    add_job(db, title="Palo Alto", location="Palo Alto, CA")
    add_job(db, title="NYC", location="Brooklyn, NY")
    add_job(db, title="Portland", location="Portland, OR")
    add_job(db, title="Boulder", location="Boulder, CO")
    assert titles(client.get(f"{BASE}&all=true&location=San Francisco Bay Area")) == ["Palo Alto", "SF"]
    assert titles(client.get(f"{BASE}&all=true&location=sf")) == ["Palo Alto", "SF"]
    assert titles(client.get(f"{BASE}&all=true&location=New York City")) == ["NYC"]
    assert titles(client.get(f"{BASE}&all=true&location=Denver / Boulder")) == ["Boulder"]
    assert titles(client.get(f"{BASE}&all=true&location=portland")) == ["Portland"]


def test_work_type_is_computed_on_save_filtered_and_returned(client, db):
    add_job(db, title="Remote job", location="Remote - US")
    add_job(db, title="Hybrid job", location="Seattle, WA", job_description="This is a hybrid role.")
    add_job(db, title="Office job", location="Chicago, IL")
    unknown = add_job(db, title="Unknown job", location="", country_codes=None)
    assert unknown.work_type is None
    body = client.get(f"{BASE}&all=true").json()
    assert {j["title"]: j["work_type"] for j in body["jobs"]} == {
        "Remote job": "remote", "Hybrid job": "hybrid", "Office job": "onsite", "Unknown job": None}
    assert titles(client.get(f"{BASE}&all=true&work_type=remote,hybrid")) == ["Hybrid job", "Remote job"]
    assert titles(client.get(f"{BASE}&all=true&work_type=onsite")) == ["Office job"]
    # an edit re-derives it
    unknown.location = "Remote"
    db.commit()
    assert unknown.work_type == "remote"


def test_save_hook_skips_unrelated_updates(db):
    job = add_job(db, title="Engineer", location="Austin, TX")
    assert job.work_type == "onsite"
    db.execute(text("UPDATE jobs SET work_type = 'hybrid' WHERE id = :i"), {"i": job.id})
    db.commit()
    db.expire_all()
    job = db.get(Job, job.id)
    job.last_seen_at = NOW
    db.commit()
    assert job.work_type == "hybrid"  # last_seen_at alone does not re-derive


def test_work_type_migration_adds_and_backfills(tmp_path):
    from migrations.job_work_type import migrate_job_work_type
    engine = create_engine(f"sqlite:///{tmp_path / 'wt.db'}")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE jobs (id INTEGER PRIMARY KEY, title TEXT, location TEXT, job_description TEXT)"))
        conn.execute(text("INSERT INTO jobs (title, location, job_description) VALUES "
                          "('A', 'Remote', NULL), ('B', 'Austin, TX', 'hybrid role'), ('C', '', NULL)"))
    with engine.connect() as conn:
        assert migrate_job_work_type(conn, commit_batches=True) == 2
        conn.commit()
    with engine.begin() as conn:
        assert "work_type" in {c["name"] for c in inspect(conn).get_columns("jobs")}
        rows = dict(conn.execute(text("SELECT title, work_type FROM jobs")).fetchall())
        assert rows == {"A": "remote", "B": "hybrid", "C": None}
        assert migrate_job_work_type(conn) == 0  # idempotent


# ---------------------------------------------------------------- salary / company / employment type

def test_salary_filter_keeps_overlapping_ranges(client, db):
    add_job(db, title="120-160", salary_min=120000, salary_max=160000)
    add_job(db, title="200-250", salary_min=200000, salary_max=250000)
    add_job(db, title="min only 90", salary_min=90000)
    add_job(db, title="no pay")
    add_job(db, title="hourly", salary_min=60, salary_max=80)
    assert titles(client.get(f"{BASE}&all=true&salary_min=150000")) == ["120-160", "200-250"]
    assert titles(client.get(f"{BASE}&all=true&salary_max=130000")) == ["120-160", "min only 90"]
    assert titles(client.get(f"{BASE}&all=true&salary_min=130000&salary_max=210000")) == ["120-160", "200-250"]


def test_company_names_case_insensitive_exact(client, db, companies):
    add_job(db, title="S", company_id=companies["Stripe"].id)
    add_job(db, title="G", company_id=companies["Google"].id)
    add_job(db, title="A", company_id=companies["Acme Robotics"].id)
    assert titles(client.get(f"{BASE}&all=true&company=stripe,ACME ROBOTICS")) == ["A", "S"]
    assert titles(client.get(f"{BASE}&all=true&company=Acme")) == []
    # combines with company_id
    assert titles(client.get(f"{BASE}&all=true&company=stripe&company_id={companies['Google'].id}")) == []


def test_employment_type_null_counts_as_full_time(client, db):
    add_job(db, title="unlabelled")
    add_job(db, title="ft", employment_type="full_time")
    add_job(db, title="intern", employment_type="internship")
    add_job(db, title="temp", employment_type="temporary")
    add_job(db, title="contract", employment_type="contract")  # never in /api/jobs
    assert titles(client.get(f"{BASE}&all=true&employment_type=full_time")) == ["ft", "unlabelled"]
    assert titles(client.get(f"{BASE}&all=true&employment_type=internship,temporary")) == ["intern", "temp"]


# ---------------------------------------------------------------- skills-based matching

@pytest.fixture
def match_jobs(db):
    add_job(db, title="Senior Backend Engineer", ai_tech_stack=["Go", "Kubernetes", "AWS"], age_days=5)
    add_job(db, title="Backend Engineer", ai_tech_stack=["Java"], age_days=1)
    add_job(db, title="Senior DevOps Engineer", ai_tech_stack=["Terraform", "AWS"], age_days=3)
    add_job(db, title="Account Executive", ai_tech_stack=["Salesforce"], age_days=0)
    add_job(db, title="Frontend Engineer", ai_tech_stack=["React", "Go"], age_days=2)


def test_match_scores_reasons_and_threshold(client, match_jobs):
    body = client.get(f"{BASE}&roles=backend&skills=go,k8s,aws&seniority=senior&sort=match&min_match=60").json()
    assert body["relevance_filtering"] is True and body["sort"] == "match"
    jobs = body["jobs"]
    assert [j["title"] for j in jobs][:2] == ["Senior Backend Engineer", "Backend Engineer"]
    top = jobs[0]
    assert top["match_score"] == 100
    assert top["match_reasons"] == ["Title matches Backend Engineer", "3 of 3 skills: go, k8s, aws", "Senior level"]
    assert all(j["match_score"] >= 60 for j in jobs)
    assert "Account Executive" not in [j["title"] for j in jobs]
    assert body["total"] == len(jobs)
    assert body["match"] == {"roles": ["Backend Engineer"], "skills": ["go", "k8s", "aws"], "seniority": "senior"}
    assert "relevance" not in top and "work_type" in top


def test_min_score_is_the_threshold_without_min_match(client, match_jobs):
    body = client.get(f"{BASE}&roles=backend&min_score=90&sort=match").json()
    assert {j["title"] for j in body["jobs"]} == {"Senior Backend Engineer", "Backend Engineer"}
    assert body["threshold"] == 90


def test_sort_recent_keeps_scored_jobs_newest_first(client, match_jobs):
    body = client.get(f"{BASE}&roles=backend,devops&sort=recent&min_match=50").json()
    assert [j["title"] for j in body["jobs"]] == [
        "Backend Engineer", "Senior DevOps Engineer", "Senior Backend Engineer"]
    assert all("match_score" in j for j in body["jobs"])


def test_skills_only_matching(client, match_jobs):
    body = client.get(f"{BASE}&skills=aws,terraform&sort=match&min_match=50").json()
    assert [(j["title"], j["match_score"]) for j in body["jobs"]] == [
        ("Senior DevOps Engineer", 100), ("Senior Backend Engineer", 50)]


def test_sort_without_roles_or_skills_lists_recent(client, match_jobs):
    body = client.get(f"{BASE}&sort=match").json()
    assert body["relevance_filtering"] is False and body["total"] == 5
    assert body["jobs"][0]["title"] == "Account Executive"


def test_bad_sort_is_400(client):
    assert client.get(f"{BASE}&sort=best").status_code == 400


def test_match_combines_with_filters(client, db, match_jobs):
    add_job(db, title="Remote Backend Engineer", location="Remote", ai_tech_stack=["Go"])
    body = client.get(f"{BASE}&roles=backend&skills=go&sort=match&work_type=remote").json()
    assert [j["title"] for j in body["jobs"]] == ["Remote Backend Engineer"]
    assert body["applied_filters"] == ["work_type"]


def test_paging_reuses_the_scored_list(client, match_jobs, monkeypatch):
    calls = []
    real = fm.score_job
    monkeypatch.setattr(fm, "score_job", lambda *a, **k: calls.append(1) or real(*a, **k))
    url = f"{BASE}&roles=backend,devops&sort=match&min_match=0&limit=2"
    first = client.get(url + "&offset=0").json()
    scored = len(calls)
    assert scored > 0
    second = client.get(url + "&offset=2").json()
    assert len(calls) == scored  # page 2 came from the cached ranking
    assert first["total"] == second["total"]
    ids = [j["id"] for j in first["jobs"]] + [j["id"] for j in second["jobs"]]
    assert len(set(ids)) == len(ids) == min(4, first["total"])
    # no_cache re-scores
    client.get(url + "&offset=0&no_cache=true")
    assert len(calls) > scored


def test_scoring_candidates_are_capped_to_most_recent(client, db, monkeypatch):
    import routes.jobs as jobs_route
    monkeypatch.setattr(jobs_route, "MAX_SCORING_CANDIDATES", 2)
    add_job(db, title="Backend Engineer old", age_days=9)
    add_job(db, title="Backend Engineer new", age_days=1)
    add_job(db, title="Backend Engineer newer", age_days=0)
    add_job(db, title="Sales Rep newest", age_days=0)  # not a title candidate
    body = client.get(f"{BASE}&roles=backend&sort=match").json()
    assert sorted(j["title"] for j in body["jobs"]) == ["Backend Engineer new", "Backend Engineer newer"]


def test_legacy_role_paging_uses_cached_ranking(client, db, monkeypatch):
    import routes.jobs as jobs_route
    for i in range(4):
        add_job(db, title=f"Senior Backend Engineer {i}", job_description="python go kubernetes microservices apis")
    calls = []
    real = jobs_route.compute_job_relevance
    monkeypatch.setattr(jobs_route, "compute_job_relevance", lambda *a, **k: calls.append(1) or real(*a, **k))
    first = client.get(f"{BASE}&role=backend&min_score=0&limit=2&offset=0").json()
    n = len(calls)
    second = client.get(f"{BASE}&role=backend&min_score=0&limit=2&offset=2").json()
    assert len(calls) == n and first["total"] == second["total"] == 4
    assert first["relevance_filtering"] is True and "relevance" in first["jobs"][0]
    assert first["jobs"][0]["job_description"]  # full rows for the page, not the scoring columns


# ---------------------------------------------------------------- facets

def test_facets_counts(client, db, companies):
    add_job(db, title="a", company_id=companies["Stripe"].id, location="Remote", salary_min=100000)
    add_job(db, title="b", company_id=companies["Stripe"].id, employment_type="internship")
    add_job(db, title="c", company_id=companies["Google"].id, location="Hybrid - NYC")
    add_job(db, title="evergreen", company_id=companies["Google"].id, is_evergreen=True)
    add_job(db, title="uk", country_codes=",GB,", location="London")
    add_job(db, title="inactive", is_active=False)
    r = client.get("/api/jobs/facets?country=US")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {
        "total": 3,
        "companies": [{"name": "Stripe", "count": 2}, {"name": "Google", "count": 1}],
        "work_type": {"remote": 1, "hybrid": 1, "onsite": 1},
        "employment_type": {"full_time": 2, "part_time": 0, "internship": 1, "temporary": 0},
        "with_salary": 1,
    }
    assert client.get("/api/jobs/facets?country=US&include_evergreen=true").json()["total"] == 4
    assert client.get("/api/jobs/facets?country=ALL").json()["total"] == 4


def test_facets_are_cached(client, db):
    add_job(db, title="a")
    assert client.get("/api/jobs/facets").json()["total"] == 1
    add_job(db, title="b")
    assert client.get("/api/jobs/facets").json()["total"] == 1  # cached 300s
    fm.clear_caches()
    assert client.get("/api/jobs/facets").json()["total"] == 2


# ---------------------------------------------------------------- detail

def test_job_detail_public_for_shared_jobs_only(client, db, users):
    shared = add_job(db, title="Shared", job_description="<p>Full posting</p>")
    private = add_job(db, title="Mine", user_id=users[0].id)
    r = client.get(f"/api/jobs/{shared.id}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_description"] == "<p>Full posting</p>" and body["work_type"] == "onsite"
    assert body["notes"] == [] and body["documents"] == [] and body["interviews"] == []
    assert client.get(f"/api/jobs/{private.id}").status_code == 404
    assert client.get(f"/api/jobs/{private.id}", headers=headers(users[1])).status_code == 404
    assert client.get(f"/api/jobs/{private.id}", headers=headers(users[0])).status_code == 200
    # a bad token is treated as anonymous
    assert client.get(f"/api/jobs/{shared.id}", headers={"Authorization": "Bearer junk"}).status_code == 200
