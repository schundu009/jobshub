"""Role category / seniority / company domain: labels on save, filters on GET /api/jobs, /facets counts."""
import pytest

from models import Company
from services import firm_matching as fm
from services import job_taxonomy as tx
from tests.test_firm_jobs_api import add_job, titles

BASE = "/api/jobs?country=ALL&include_evergreen=false&all=true"


@pytest.mark.parametrize("title,level", [
    ("Software Engineer Intern", "intern"),
    ("Internal Tools Engineer", "mid"),
    ("Director, Platform Engineering", "director_exec"),
    ("Associate Director of Data", "director_exec"),
    ("Engineering Manager, Payments", "manager"),
    ("Senior Product Manager", "senior"),
    ("Product Manager", "mid"),
    ("Staff Software Engineer", "lead_staff"),
    ("Tech Lead, Search", "lead_staff"),
    ("Sr. DevOps Engineer", "senior"),
    ("Software Engineer III", "senior"),
    ("Software Engineer I", "entry"),
    ("New Grad Software Engineer", "entry"),
    ("Software Engineer II", "mid"),
    ("Backend Engineer", "mid"),
    ("Product Manager, Technology", "mid"),
    ("Full Stack Java Developer Tech Lead- Vice President", "lead_staff"),
    ("Chase Auto Product Manager, Vice President", "senior"),
    ("Software Engineer III - Associate", "senior"),
    ("Engineering Manager, Payments - Vice President", "manager"),
])
def test_seniority(title, level):
    assert tx.seniority(title) == level


def test_company_domain_normalizes_names():
    assert tx.company_domain("Netflix") == "streaming_media"
    assert tx.company_domain("netflix, inc.") == "streaming_media"
    assert tx.company_domain("Nobody Heard Of This Co 123") is None


def test_labels_set_on_save(db):
    c = Company(name="Netflix")
    db.add(c)
    db.commit()
    assert c.domain == "streaming_media"
    job = add_job(db, title="Senior Site Reliability Engineer", company_id=c.id)
    assert (job.role_category, job.seniority) == ("devops_sre_cloud", "senior")
    job.title = "Staff Data Engineer"
    db.commit()
    assert (job.role_category, job.seniority) == ("data", "lead_staff")


@pytest.fixture
def mix(db):
    fm.clear_caches()
    netflix, chase = Company(name="Netflix"), Company(name="JPMorgan Chase")
    db.add_all([netflix, chase])
    db.commit()
    add_job(db, title="Senior Backend Engineer", company_id=netflix.id)
    add_job(db, title="Site Reliability Engineer", company_id=netflix.id, country_codes=",GB,", location="London")
    add_job(db, title="Staff Data Engineer", company_id=chase.id)
    add_job(db, title="Software Engineer Intern", company_id=chase.id, citizenship_restricted=True)


def test_filters(client, mix):
    assert titles(client.get(f"{BASE}&role_category=devops_sre_cloud,data")) == [
        "Site Reliability Engineer", "Staff Data Engineer"]
    assert titles(client.get(f"{BASE}&seniority_level=senior,intern")) == [
        "Senior Backend Engineer", "Software Engineer Intern"]
    assert titles(client.get(f"{BASE}&domain=streaming_media&seniority_level=mid")) == ["Site Reliability Engineer"]
    assert titles(client.get(f"{BASE}&countries=GB")) == ["Site Reliability Engineer"]
    assert "Software Engineer Intern" not in titles(client.get(f"{BASE}&visa_ok=true"))
    assert titles(client.get(f"{BASE}&q=london")) == ["Site Reliability Engineer"]  # search covers location
    body = client.get(f"{BASE}&role_category=data&domain=banking&countries=US&visa_ok=true").json()
    assert body["applied_filters"] == ["role_category", "domain", "countries", "visa"]


def test_facets_leave_their_own_filter_out(client, mix):
    body = client.get("/api/jobs/facets?country=ALL&domain=streaming_media&seniority_level=senior").json()
    assert body["total"] == 1  # every filter applied, as the list
    domains = {d["value"]: d["count"] for d in body["domain"]}
    assert domains["streaming_media"] == 1 and domains["banking"] == 0  # seniority applies, domain does not
    levels = {d["value"]: d["count"] for d in body["seniority"]}
    assert levels == {**{k: 0 for k in tx.SENIORITIES}, "senior": 1, "mid": 1}  # Netflix only
    assert [d["value"] for d in body["role_category"]] == list(tx.ROLE_CATEGORIES)
    plain = client.get("/api/jobs/facets?country=ALL").json()
    assert plain["total"] == 4 and plain["visa_ok"] == 3
    assert {c["code"]: c["count"] for c in plain["countries"]} == {"US": 3, "GB": 1}


def test_list_total_matches_facets_total(client, mix):
    qs = "domain=banking,streaming_media&role_category=software,data&countries=US"
    listed = client.get(f"{BASE}&{qs}").json()["total"]
    assert listed == client.get(f"/api/jobs/facets?country=ALL&{qs}").json()["total"] == 3


def test_taxonomy_endpoint(client):
    body = client.get("/api/jobs/taxonomy").json()
    assert [d["value"] for d in body["domains"]] == list(tx.DOMAINS)
    assert body["seniorities"][0] == {"value": "intern", "label": "Intern"}


def test_rank_only_orders_without_narrowing(client, mix):
    qs = "country=ALL&include_evergreen=false&roles=sre&skills=kubernetes&rank_only=true&limit=10"
    body = client.get(f"/api/jobs?{qs}").json()
    assert body["total"] == 4 == client.get("/api/jobs/facets?country=ALL").json()["total"]
    assert body["jobs"][0]["title"] == "Site Reliability Engineer"
    scores = [j["match_score"] for j in body["jobs"]]
    assert scores == sorted(scores, reverse=True)
