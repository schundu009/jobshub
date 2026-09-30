"""contracts.service (30-day window, dedupe, expiry) and the public /api/contracts API."""
from datetime import datetime, timedelta

import pytest

from contracts import service
from contracts.models import ContractJob
from models import AppSetting, User
from scrapers.base import ScrapedJob
from utils.security import create_access_token

NOW = datetime.utcnow()


def sj(i, **kw):
    fields = dict(title=f"Java Developer {i}", location="Austin, TX", job_url=f"https://agency.example/j/{i}",
                  external_job_id=str(i), posted_date=NOW - timedelta(days=2),
                  job_description="6 month contract. W2 only. $65/hr. USC/GC only.")
    fields.update(kw)
    return ScrapedJob(**fields)


# ------------------------------------------------------------------ service

def test_save_classifies_and_dedupes(db):
    r = service.save_contract_jobs(db, "agency", [sj(1), sj(1), sj(2, title="")], agency_name="Agency")
    assert (r.new, r.duplicates, r.skipped_invalid) == (1, 1, 1)
    row = db.query(ContractJob).one()
    assert row.employment_type == "contract" and row.tax_terms == ["w2"] and row.visa_terms == ["usc_gc_only", "no_c2c"]
    assert (row.pay_rate_min, row.pay_period, row.hourly_rate_min, row.hourly_rate_max) == (65.0, "hour", 65.0, 65.0)
    assert row.contract_duration_months == 6 and row.country_codes == ",US," and row.agency_name == "Agency"
    assert row.first_seen_at == row.last_seen_at and row.skills == ["java"]

    r2 = service.save_contract_jobs(db, "agency", [sj(1, title="Senior Java Developer")])
    assert (r2.new, r2.updated) == (0, 1)
    assert db.query(ContractJob).one().title == "Senior Java Developer"


def test_thirty_day_window_and_setting(db):
    old = sj(1, posted_date=NOW - timedelta(days=31))
    assert service.save_contract_jobs(db, "agency", [old]).skipped_old == 1
    db.add(AppSetting(key="contract_max_age_days", value="45"))
    db.commit()
    assert service.save_contract_jobs(db, "agency", [old]).new == 1


def test_redated_posting_keeps_first_seen_and_expires(db):
    service.save_contract_jobs(db, "agency", [sj(1)], now=NOW - timedelta(days=40))
    # Board re-dates it to today; our first sighting (40 days ago) wins -> expired.
    r = service.save_contract_jobs(db, "agency", [sj(1, posted_date=NOW)], now=NOW)
    assert (r.skipped_old, r.expired) == (1, 1)
    assert db.query(ContractJob).one().is_active is False


def test_expire_and_deactivate_unseen(db):
    service.save_contract_jobs(db, "agency", [sj(1), sj(2), sj(3)])
    db.query(ContractJob).filter(ContractJob.external_job_id == "1").update(
        {"effective_posted_at": NOW - timedelta(days=31)})
    db.commit()
    assert service.expire_contract_jobs(db) == 1
    assert service.deactivate_unseen(db, "agency", {"2"}) == 1
    assert {r.external_job_id for r in db.query(ContractJob).filter(ContractJob.is_active == True)} == {"2"}  # noqa: E712


def test_staffing_direct_hire_is_skipped(db):
    r = service.save_contract_jobs(db, "agency", [sj(1, employment_type_raw="Direct Hire / Permanent", job_description="")])
    assert r.skipped_not_contract == 1 and db.query(ContractJob).count() == 0


def test_pay_normalized_to_hourly(db):
    service.save_contract_jobs(db, "agency", [sj(1, job_description="Contract. $600/day"),
                                              sj(2, job_description="Contract. $124,800 per year")])
    rows = {r.external_job_id: r for r in db.query(ContractJob)}
    assert rows["1"].hourly_rate_min == 75.0 and rows["2"].hourly_rate_min == 60.0


# ------------------------------------------------------------------ API

@pytest.fixture
def seeded(db):
    jobs = [
        sj(1, title="Java Developer", job_description="12 month contract. W2 only. $70/hr. USC/GC only. Java, Spring"),
        sj(2, title="Python Engineer", location="Remote - US",
           job_description="Contract to hire. C2C ok. $80-$95/hr. H1B ok. Duration: 6 months"),
        sj(3, title="Data Analyst", location="Toronto, ON", job_description="Contract role. $50/hr"),
        sj(4, title="QA Tester", location="Remote", job_description="Temporary assignment, 3 months, $30/hr"),
        sj(5, title="Security Engineer", location="Herndon, VA",
           job_description="Contract role. TS/SCI clearance required. $120,000 - $140,000 per year. 1099"),
    ]
    service.save_contract_jobs(db, "agency", jobs, agency_name="Acme Staffing")
    return {r.external_job_id: r.id for r in db.query(ContractJob)}


def ids(resp, seeded):
    back = {v: k for k, v in seeded.items()}
    return sorted(back[j["id"]] for j in resp.json()["jobs"])


def test_public_list_defaults_to_us_plus_unknown(client, seeded):
    r = client.get("/api/contracts/jobs")
    assert r.status_code == 200 and r.json()["country"] == "US"
    assert ids(r, seeded) == ["1", "2", "4", "5"]  # Toronto hidden, "Remote" (unknown) visible
    item = next(j for j in r.json()["jobs"] if j["title"] == "Java Developer")
    for key in ("employment_type", "tax_terms", "pay_rate_min", "pay_rate_max", "pay_period", "hourly_rate_min",
                "contract_duration_months", "visa_terms", "country_codes", "agency_name", "end_client",
                "apply_url", "listed_since", "listed_days", "skills"):
        assert key in item
    assert item["apply_url"].startswith("https://") and item["listed_since"].endswith("Z")
    assert item["country_codes"] == ["US"] and "description" not in item


def test_country_and_confirmed_only(client, seeded):
    assert ids(client.get("/api/contracts/jobs?country=CA"), seeded) == ["3", "4"]
    assert ids(client.get("/api/contracts/jobs?confirmed_only=true"), seeded) == ["1", "2", "5"]
    assert ids(client.get("/api/contracts/jobs?country=ALL"), seeded) == ["1", "2", "3", "4", "5"]
    assert client.get("/api/contracts/jobs?country=Narnia").status_code == 400


@pytest.mark.parametrize("query, expected", [
    ("employment_type=contract_to_hire", ["2"]),
    ("employment_type=temporary,contract_to_hire", ["2", "4"]),
    ("employment_type=contract_any", ["1", "2", "4", "5"]),
    ("tax_terms=c2c", ["2"]),
    ("tax_terms=w2,1099", ["1", "5"]),
    ("min_rate=75", ["2"]),
    ("max_rate=40", ["4"]),
    ("min_rate=60&include_salary_equiv=true", ["1", "2", "5"]),
    ("min_duration_months=12", ["1"]),
    ("visa=h1b_ok", ["2"]),
    ("exclude_visa=usc_gc_only,security_clearance", ["2", "4"]),
    ("q=java", ["1"]),
    ("agency=acme staffing", ["1", "2", "4", "5"]),
    ("location=herndon", ["5"]),
    ("remote=true", ["2", "4"]),
])
def test_filters(client, seeded, query, expected):
    r = client.get(f"/api/contracts/jobs?{query}")
    assert r.status_code == 200, r.text
    assert ids(r, seeded) == expected


def test_sort_limit_and_description(client, seeded):
    r = client.get("/api/contracts/jobs?sort=rate&limit=2&description_chars=60")
    body = r.json()
    assert body["total"] == 4 and len(body["jobs"]) == 2 and body["jobs"][0]["title"] == "Python Engineer"
    assert len(body["jobs"][0]["description"]) <= 60
    assert client.get("/api/contracts/jobs?limit=101").status_code == 422
    assert client.get("/api/contracts/jobs?employment_type=full_time").status_code == 400
    assert client.get("/api/contracts/jobs?sort=salary").status_code == 400


def test_detail_and_facets(client, seeded):
    d = client.get(f"/api/contracts/jobs/{seeded['1']}").json()
    assert "Java, Spring" in d["description"] and d["description_text"]
    assert client.get("/api/contracts/jobs/999999").status_code == 404
    f = client.get("/api/contracts/facets").json()
    assert f["total"] == 4 and f["country"] == "US"
    assert f["employment_type"] == {"contract": 2, "contract_to_hire": 1, "temporary": 1, "freelance": 0}
    assert f["tax_terms"] == {"w2": 1, "c2c": 1, "1099": 1}
    assert f["visa_terms"]["usc_gc_only"] == 1 and f["agencies"] == [{"name": "Acme Staffing", "count": 4}]


def test_cors_preflight_for_cariara(client):
    r = client.options("/api/contracts/jobs", headers={
        "Origin": "https://cariara.com", "Access-Control-Request-Method": "GET"})
    assert r.status_code == 200 and r.headers.get("access-control-allow-origin") == "https://cariara.com"


def test_admin_endpoints_require_admin(client, db, users, seeded):
    assert client.get("/api/contracts/status").status_code in (401, 403)
    token, _ = create_access_token(users[0].id, users[0].email)
    users[0].role = "user"
    db.commit()
    assert client.get("/api/contracts/status", headers={"Authorization": f"Bearer {token}"}).status_code == 403
    users[0].role = "admin"
    db.commit()
    body = client.get("/api/contracts/status", headers={"Authorization": f"Bearer {token}"}).json()
    assert body["contract_max_age_days"] == 30 and body["active_total"] == 5
    assert body["sources"][0]["source"] == "agency"
