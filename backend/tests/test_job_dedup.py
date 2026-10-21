"""jobs.dedup_key (services.job_dedup): a posting listed more than once shows once in /api/jobs and its facets."""
from datetime import datetime, timedelta

from models import Company, Job
from services.job_dedup import dedup_key, pay_key
from contracts.classifier import contract_routing
from contracts.vendors import is_contract_vendor

NOW = datetime.utcnow()
JD = ("<p>Slack is hiring a staff engineer for the data platform. You will design pipelines, own reliability "
      "and mentor engineers across the team. We work in Spark, Airflow and Kafka, and ship to production weekly. "
      "You bring eight years of building data systems at scale, clear writing and calm on-call judgement. "
      "The team partners with analytics, machine learning and product groups on a shared roadmap.</p>")


def add_job(db, ext, company, **kw):
    fields = dict(title="Staff Data Platform Engineer", location="San Francisco, CA", source="workday",
                  external_job_id=str(ext), company_id=company.id, is_active=True, status="wishlist",
                  posted_date=NOW - timedelta(days=2), first_seen_at=NOW - timedelta(days=2),
                  effective_posted_at=NOW - timedelta(days=2), country_codes=",US,", is_evergreen=False,
                  job_description=JD)
    fields.update(kw)
    job = Job(**fields)
    db.add(job)
    db.commit()
    return job


def company(db, name):
    c = Company(name=name)
    db.add(c)
    db.commit()
    return c


def test_key_rules():
    same = dedup_key("Staff Engineer", 1, "SF", JD)
    assert same == dedup_key("staff  engineer", 2, "New York", JD.replace("<p>", ""))  # boards and cities
    assert same != dedup_key("Principal Engineer", 1, "SF", JD)
    assert same != dedup_key("Staff Engineer", 1, "SF", JD + " Also Go.")
    # No description: the title, company and location decide.
    assert dedup_key("MRI Technologist", 1, "Moline, IL", "") == dedup_key("MRI Technologist", 1, "Moline, IL", None)
    assert dedup_key("MRI Technologist", 1, "Moline, IL", "") != dedup_key("MRI Technologist", 1, "Nashville, TN", "")
    assert dedup_key("", 1, "x", JD) is None


def test_save_hook_sets_and_refreshes_the_key(db):
    job = add_job(db, 1, company(db, "Salesforce"))
    assert job.dedup_key == dedup_key(job.title, job.company_id, job.location, JD)
    job.title = "Principal Data Platform Engineer"
    db.commit()
    assert job.dedup_key == dedup_key("Principal Data Platform Engineer", job.company_id, job.location, JD)


def test_list_and_facets_show_a_posting_once(client, db):
    sf, slack = company(db, "Salesforce"), company(db, "Slack")
    first = add_job(db, 1, sf)
    add_job(db, 2, slack, location="New York, NY")
    add_job(db, 3, slack, title="Other role", job_description="")
    body = client.get("/api/jobs?all=true&no_cache=true").json()
    assert sorted((j["id"], j["title"]) for j in body["jobs"]) == sorted(
        [(first.id, "Staff Data Platform Engineer"), (first.id + 2, "Other role")])
    assert body["total"] == 2
    assert client.get("/api/jobs/facets?no_cache=true").json()["total"] == 2
    # A filter that keeps only the other copy still finds it.
    ny = client.get("/api/jobs?all=true&no_cache=true&company=Slack").json()["jobs"]
    assert sorted(j["title"] for j in ny) == ["Other role", "Staff Data Platform Engineer"]


def test_pay_key_rules():
    key = pay_key("Forward Deployed Engineer", 1, "Mountain View, California", 171000, 231500)
    assert key == pay_key("forward  deployed engineer", 1, "Mountain View, California", 171000, 231500)
    assert key != pay_key("Forward Deployed Engineer", 1, "Mountain View, California", 202500, 274000)  # another level
    assert key != pay_key("Forward Deployed Engineer", 1, "New York, New York", 171000, 231500)
    assert key != pay_key("Forward Deployed Engineer", 2, "Mountain View, California", 171000, 231500)
    # No pay range: the title alone is too broad to merge on.
    assert pay_key("Software Engineer", 1, "Mountain View, California", None, None) is None
    assert pay_key("", 1, "x", 1, 2) is None


def test_one_role_opened_several_times_shows_once(client, db):
    intuit = company(db, "Intuit")
    pay = dict(title="Forward Deployed Engineer", location="Mountain View, California",
               salary_min=171000, salary_max=231500)
    first = add_job(db, 1, intuit, job_description=JD + " Team: invoicing.", **pay)
    add_job(db, 2, intuit, job_description=JD + " Team: payments.", **pay)
    add_job(db, 3, intuit, job_description=JD + " Team: payroll.", **pay)
    other_level = add_job(db, 4, intuit, job_description=JD + " Team: tax.",
                          **{**pay, "salary_min": 202500, "salary_max": 274000})
    no_pay = add_job(db, 5, intuit, title="Software Engineer", job_description=JD + " A.")
    add_job(db, 6, intuit, title="Software Engineer", job_description=JD + " B.")
    assert first.pay_key and first.pay_key == pay_key(pay["title"], intuit.id, pay["location"], 171000, 231500)
    body = client.get("/api/jobs?all=true&no_cache=true").json()
    ids = sorted(j["id"] for j in body["jobs"])
    # One card per level; the no-pay "Software Engineer" postings differ in text, so both stay.
    assert ids == sorted([first.id, other_level.id, no_pay.id, no_pay.id + 1])
    assert body["total"] == 4
    assert client.get("/api/jobs/facets?no_cache=true").json()["total"] == 4


def test_save_hook_refreshes_the_pay_key(db):
    job = add_job(db, 1, company(db, "Intuit"), salary_min=100000, salary_max=150000)
    before = job.pay_key
    assert before
    job.salary_max = 160000
    db.commit()
    assert job.pay_key and job.pay_key != before


def test_staffing_vendors_route_their_contract_reqs():
    assert is_contract_vendor("Akraya, Inc.") and is_contract_vendor("VDart") and is_contract_vendor("yochana")
    assert not is_contract_vendor("Michael Page") and not is_contract_vendor("Target") and not is_contract_vendor(None)
    rate = "Location: Houston, TX. Rate - $55/hr. Customer interview in person. HubSpot workflows and reporting."
    assert contract_routing("HubSpot Marketing Specialist", rate, None, staffing=True) == (True, "contract")
    assert contract_routing("HubSpot Marketing Specialist", rate, None, staffing=False)[0] is False
    c2c = "Remote. Subcon rate $60/hr C2C / $50 W2. Release management for a bank."
    assert contract_routing("IT Release Manager", c2c, None, staffing=True)[0] is True
    assert contract_routing("OnBase Developer", "Senior Lead Onbase Hyland Developer Remote Contract JD Creates objects.",
                            None, staffing=True) == (True, "contract")
    assert contract_routing("Backend Engineer", "Full time role with benefits, $150K-$180K a year.", None,
                            staffing=True)[0] is False
