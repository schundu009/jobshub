"""Search (q / loc), profile matching, descriptions on demand, the non-IT safety
net and the cleanup scripts (reroute_company_board_rows, deactivate_non_it).
No network: description fetches are monkeypatched."""
from datetime import datetime, timedelta

import pytest

from contracts import descriptions, service
from contracts.matching import build_profile, score_job, title_level
from contracts.models import ContractJob
from models import Company, Job
from scrapers.base import ScrapedJob

NOW = datetime.utcnow()


def sj(i, **kw):
    fields = dict(title=f"Java Developer {i}", location="Austin, TX", job_url=f"https://agency.example/j/{i}",
                  external_job_id=str(i), posted_date=NOW - timedelta(days=2),
                  job_description="6 month contract. W2 only. $65/hr.")
    fields.update(kw)
    return ScrapedJob(**fields)


def add(db, i, title, location="Austin, TX", skills=None, description="Contract role", source="agency",
        source_type="staffing", days=2, job_url=None, **kw):
    row = ContractJob(source=source, source_type=source_type, external_job_id=str(i), title=title,
                      location=location, country_codes=",US,", description=description, skills=skills,
                      job_url=job_url or f"https://agency.example/j/{i}", is_active=True,
                      employment_type="contract", effective_posted_at=NOW - timedelta(days=days),
                      first_seen_at=NOW - timedelta(days=days), agency_name="Acme", **kw)
    db.add(row)
    db.commit()
    return row


def titles(resp):
    assert resp.status_code == 200, resp.text
    return [j["title"] for j in resp.json()["jobs"]]


# ------------------------------------------------------------------ q search

@pytest.fixture
def search_rows(db):
    add(db, 1, "DevOps Engineer", skills=["aws", "terraform"])
    add(db, 2, "Business Systems Analyst", skills=["sql"],
        description="Work with the DevOps team on release planning.")
    add(db, 3, "Go Developer", skills=["go", "kubernetes"], location="San Jose, CA")
    add(db, 4, "Google Ads Specialist", skills=["sem"], location="Sacramento, California")
    add(db, 5, "Senior Java Developer", skills=["java", "spring"], location="Remote")
    add(db, 6, "Data Engineer", skills=["python"], end_client="Walmart", location="Bentonville, AR")


def test_q_matches_title_skills_agency_not_description(client, search_rows):
    assert titles(client.get("/api/contracts/jobs?q=devops")) == ["DevOps Engineer"]
    assert sorted(titles(client.get("/api/contracts/jobs?q=devops&q_description=true"))) == \
        ["Business Systems Analyst", "DevOps Engineer"]
    assert titles(client.get("/api/contracts/jobs?q=walmart")) == ["Data Engineer"]
    assert titles(client.get("/api/contracts/jobs?q=terraform")) == ["DevOps Engineer"]


def test_q_all_words_must_match_case_insensitive(client, search_rows):
    assert titles(client.get("/api/contracts/jobs?q=SENIOR%20java")) == ["Senior Java Developer"]
    assert titles(client.get("/api/contracts/jobs?q=senior%20python")) == []


def test_q_short_tokens_are_word_bounded(client, search_rows):
    # "go" must not match "Google"
    assert titles(client.get("/api/contracts/jobs?q=go")) == ["Go Developer"]


@pytest.mark.parametrize("param,value,expected", [
    ("location", "california", ["Google Ads Specialist", "Go Developer"]),
    ("loc", "CA", ["Google Ads Specialist", "Go Developer"]),
    ("loc", "ca", ["Google Ads Specialist", "Go Developer"]),
    ("location", "san jose", ["Go Developer"]),
    ("location", "Arkansas", ["Data Engineer"]),
    ("location", "remote", ["Senior Java Developer"]),
    ("location", "texas", ["DevOps Engineer", "Business Systems Analyst"]),
])
def test_location_text_or_state(client, search_rows, param, value, expected):
    assert sorted(titles(client.get(f"/api/contracts/jobs?{param}={value}"))) == sorted(expected)


# ------------------------------------------------------------------ matching (pure)

def test_score_title_skills_seniority():
    p = build_profile("DevOps Engineer,SRE,platform", "terraform, AWS, k8s, python, go, ansible, jenkins, helm", "senior")
    score, reasons = score_job("Senior DevOps Engineer", ["aws", "terraform", "kubernetes", "python", "docker"], p)
    assert score >= 80
    assert reasons[0] == "Title matches DevOps Engineer"
    assert reasons[1].startswith("4 of 8 skills: terraform, AWS, k8s, python")
    assert "Senior level" in reasons
    low, low_reasons = score_job("Business Systems Analyst", ["sql"], p)
    assert low < 30 and not any(r.startswith("Title") for r in low_reasons)


def test_related_roles_score_between():
    p = build_profile("SRE", None, None)
    exact, _ = score_job("Site Reliability Engineer", [], p)
    related, reasons = score_job("Cloud Platform Engineer", [], p)
    none, _ = score_job("Payroll Analyst", [], p)
    assert exact == 100 and 40 <= related < 100 and none < 25
    assert reasons == ["Title related to SRE"]


def test_free_text_role_and_skill_aliases():
    p = build_profile("Salesforce Developer", "sfdc, apex", None)
    s, reasons = score_job("Salesforce Developer - Remote", ["salesforce"], p)
    assert s >= 75 and reasons[0] == "Title matches Salesforce Developer"
    assert build_profile(None, "K8s, Golang, JS", None).skills == ["kubernetes", "go", "javascript"]


def test_no_profile_no_score():
    assert score_job("Anything", [], build_profile(None, None, "senior")) == (None, None)


@pytest.mark.parametrize("title,level", [
    ("Sr. Java Developer", "senior"), ("Junior QA Analyst", "junior"), ("Staff Engineer", "lead"),
    ("Principal Architect", "principal"), ("Software Engineer II", "mid"), ("Data Engineer", None),
])
def test_title_level(title, level):
    assert title_level(title) == level


# ------------------------------------------------------------------ matching (API)

@pytest.fixture
def match_rows(db):
    add(db, 1, "Senior DevOps Engineer", skills=["aws", "terraform", "kubernetes"], days=5)
    add(db, 2, "Site Reliability Engineer", skills=["python", "kubernetes"], days=1)
    add(db, 3, "Business Systems Analyst", skills=["sql", "devops"], days=0)
    add(db, 4, "Payroll Specialist", skills=[], days=3)


def test_api_match_fields_sort_and_min(client, match_rows):
    base = "/api/contracts/jobs?roles=DevOps%20Engineer,SRE&skills=terraform,aws,kubernetes&seniority=senior"
    body = client.get(base + "&sort=match").json()
    got = [(j["title"], j["match_score"]) for j in body["jobs"]]
    assert got[0][0] == "Senior DevOps Engineer" and got[1][0] == "Site Reliability Engineer"
    assert [s for _, s in got] == sorted([s for _, s in got], reverse=True)
    assert body["jobs"][0]["match_reasons"][0] == "Title matches DevOps Engineer"
    assert body["total"] == 4 and body["match_candidates_capped"] is False

    strict = client.get(base + "&min_match=60").json()
    assert {j["title"] for j in strict["jobs"]} == {"Senior DevOps Engineer", "Site Reliability Engineer"}
    assert strict["total"] == 2

    plain = client.get("/api/contracts/jobs").json()
    assert all(j["match_score"] is None and j["match_reasons"] is None for j in plain["jobs"])
    recent = client.get(base).json()  # default sort=recent, scores still attached
    assert recent["jobs"][0]["title"] == "Business Systems Analyst" and recent["jobs"][0]["match_score"] is not None


def test_api_match_validation(client, match_rows):
    assert client.get("/api/contracts/jobs?sort=match").status_code == 400
    assert client.get("/api/contracts/jobs?min_match=50").status_code == 400
    assert client.get("/api/contracts/jobs?roles=devops&seniority=wizard").status_code == 400
    assert client.get("/api/contracts/jobs?roles=devops&min_match=101").status_code == 422


def test_api_skills_only_match(client, match_rows):
    body = client.get("/api/contracts/jobs?skills=kubernetes,python&min_match=50&sort=match").json()
    assert [j["title"] for j in body["jobs"]] == ["Site Reliability Engineer", "Senior DevOps Engineer"]


# ------------------------------------------------------------------ descriptions on demand

def test_description_stored_fetched_unavailable(client, db, monkeypatch):
    stored = add(db, 1, "Java Developer", description="<p>Build APIs</p>")
    empty = add(db, 2, "Cloud Engineer", description=None, source="collabera",
                job_url="https://www.collabera.com/job-description/?post=1")
    other = add(db, 3, "QA Tester", description=None, source="unknownsrc")
    calls = []

    def fake(source, url, deadline=descriptions.DEADLINE):
        calls.append((source, url))
        return "<p>Terraform and AWS on a 6 month contract.</p>", "Terraform and AWS on a 6 month contract."

    monkeypatch.setattr(descriptions, "fetch_with_deadline", fake)
    d1 = client.get(f"/api/contracts/jobs/{stored.id}").json()
    assert d1["description_status"] == "stored" and calls == []
    d2 = client.get(f"/api/contracts/jobs/{empty.id}").json()
    assert d2["description_status"] == "fetched" and "Terraform" in d2["description_text"]
    db.refresh(empty)
    assert "Terraform" in empty.description and "terraform" in (empty.skills or [])
    assert client.get(f"/api/contracts/jobs/{empty.id}").json()["description_status"] == "stored"
    assert client.get(f"/api/contracts/jobs/{other.id}").json()["description_status"] == "unavailable"
    assert len(calls) == 1


def test_description_fetch_failure_is_unavailable_and_backs_off(client, db, monkeypatch):
    row = add(db, 1, "Cloud Engineer", description=None, source="insightglobal",
              job_url="https://insightglobal.com/jobs/1")
    calls = []
    monkeypatch.setattr(descriptions, "fetch_with_deadline", lambda *a, **k: calls.append(a) or (None, None))
    descriptions._failed.clear()
    assert client.get(f"/api/contracts/jobs/{row.id}").json()["description_status"] == "unavailable"
    assert client.get(f"/api/contracts/jobs/{row.id}").json()["description_status"] == "unavailable"
    assert len(calls) == 1  # negative cache
    descriptions._failed.clear()


def test_fetch_with_deadline_never_blocks(monkeypatch):
    import time as _t

    def slow(url):
        _t.sleep(2)
        return "<p>x</p>", "x"

    monkeypatch.setattr(descriptions, "_fetcher", lambda source: slow)
    start = _t.time()
    assert descriptions.fetch_with_deadline("collabera", "https://x.example/j", deadline=0.2) == (None, None)
    assert _t.time() - start < 1.0

    def boom(url):
        raise descriptions.FetchBlocked("robots")

    monkeypatch.setattr(descriptions, "_fetcher", lambda source: boom)
    assert descriptions.fetch_with_deadline("collabera", "https://x.example/j") == (None, None)


def test_polite_get_respects_robots(monkeypatch):
    monkeypatch.setattr(descriptions, "robots_allowed", lambda url, timeout=10: False)
    with pytest.raises(descriptions.FetchBlocked):
        descriptions.polite_get("https://example.com/jobs/1")
    with pytest.raises(descriptions.FetchBlocked):
        descriptions.polite_get("file:///etc/passwd")


def test_html_to_text():
    assert descriptions.html_to_text("<p>One</p><ul><li>A</li><li>B</li></ul>") == "One\n- A\n- B"
    assert descriptions.html_to_text("") is None


# ------------------------------------------------------------------ non-IT safety net

def test_save_skips_non_it(db):
    r = service.save_contract_jobs(db, "agency", [
        sj(1, title="Java Developer"),
        sj(2, title="Registered Nurse"),
        sj(3, title="Warehouse Associate"),
        sj(4, title="Consultant"),  # undecided -> kept (only confident non-IT is dropped)
        sj(6, title="Scientist"),  # lean-out -> kept
        sj(7, title="Program Manager - Change Management"),  # qualifier_out -> dropped
    ])
    assert (r.new, r.skipped_non_it) == (3, 3)
    r2 = service.save_contract_jobs(db, "agency2", [sj(5, title="Registered Nurse")], it_only=False)
    assert r2.new == 1


def test_deactivate_non_it_script(db):
    from contracts.scripts.deactivate_non_it import main
    add(db, 1, "Java Developer")
    add(db, 2, "Registered Nurse")
    add(db, 3, "Consultant")
    add(db, 4, "Technician")
    dry = main([], db=db)
    assert dry["non_it"] == 1 and db.query(ContractJob).filter(ContractJob.is_active == True).count() == 4  # noqa: E712
    assert main(["--include-uncertain"], db=db)["non_it"] == 3
    done = main(["--apply"], db=db)
    assert done["non_it"] == 1
    assert {r.title for r in db.query(ContractJob).filter(ContractJob.is_active == True)} == \
        {"Java Developer", "Consultant", "Technician"}  # noqa: E712


# ------------------------------------------------------------------ reroute script

def test_reroute_company_board_rows(db):
    from contracts.scripts.reroute_company_board_rows import main
    co = Company(name="Reddit")
    db.add(co)
    db.commit()
    # the prod misroute: full-time role moved out of jobs by description boilerplate
    db.add(Job(title="Senior Director, Data Science", company_id=co.id, source="reddit", external_job_id="8226397",
               is_active=False, employment_type="contract"))
    db.commit()
    add(db, 1, "Senior Director, Data Science", source="reddit", source_type="company_board",
        company_id=co.id).external_job_id = "8226397"
    db.commit()
    add(db, 2, "Java Developer (Contract)", source="reddit", source_type="company_board", company_id=co.id)
    add(db, 3, "Frontend Engineer", source="reddit", source_type="company_board")  # no jobs row
    add(db, 4, "Nurse", source="agency", source_type="staffing")  # staffing rows untouched

    dry = main([], db=db)
    assert dry["totals"] == {"scanned": 3, "kept": 1, "not_contract": 2, "jobs_reactivated": 1, "no_jobs_row": 1}
    assert db.query(ContractJob).filter(ContractJob.is_active == True).count() == 4  # noqa: E712

    main(["--apply"], db=db)
    active = {r.title for r in db.query(ContractJob).filter(ContractJob.is_active == True)}  # noqa: E712
    assert active == {"Java Developer (Contract)", "Nurse"}
    job = db.query(Job).filter(Job.external_job_id == "8226397").one()
    assert job.is_active is True and job.employment_type is None
    assert main([], db=db)["scanned"] == 1  # idempotent
