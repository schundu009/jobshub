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


def test_location_any_of_and_list_orders(client, db, mix):
    assert titles(client.get(f"{BASE}&location=London|Austin")) == sorted(
        ["Senior Backend Engineer", "Site Reliability Engineer", "Staff Data Engineer", "Software Engineer Intern"])
    assert titles(client.get(f"{BASE}&location=London")) == ["Site Reliability Engineer"]
    names = [j["company_name"] for j in client.get("/api/jobs?country=ALL&include_evergreen=false&sort=company").json()["jobs"]]
    assert names == sorted(names)
    assert client.get("/api/jobs?sort=bogus").status_code == 400
    locs = client.get("/api/jobs/facets?country=ALL&location=London").json()["locations"]
    assert {loc["name"]: loc["count"] for loc in locs} == {"Austin, TX": 3, "London": 1}  # own filter left out


def test_short_place_tokens_match_whole_words(client, db):
    fm.clear_caches()
    add_job(db, title="A", location="Chicago, IL")
    add_job(db, title="B", location="San Jose, CA")
    assert titles(client.get(f"{BASE}&location=CA")) == ["B"]


def test_relabel_forward_deployed_moves_only_fde_titles(db):
    from sqlalchemy import text
    from migrations.job_taxonomy import relabel_forward_deployed
    c = Company(name="Palantir")
    db.add(c)
    db.commit()
    fde = add_job(db, title="Forward Deployed Software Engineer", company_id=c.id)
    swe = add_job(db, title="Software Engineer", company_id=c.id)
    assert fde.role_category == "forward_deployed"  # new rows are labelled on save
    # A row labelled before the category existed.
    db.execute(text("UPDATE jobs SET role_category = 'software' WHERE id = :i"), {"i": fde.id})
    db.commit()
    conn = db.connection()
    assert relabel_forward_deployed(conn) == 1
    assert relabel_forward_deployed(conn) == 0  # idempotent
    db.commit()
    cats = dict(db.execute(text("SELECT id, role_category FROM jobs")).fetchall())
    assert cats[fde.id] == "forward_deployed" and cats[swe.id] == "software"


# ------------------------------------------------------------------ the job description decides
_TERADYNE_JD = (
    "The Power Infrastructure Team builds next-generation Semiconductor Testers. Tester Power Subassembly Design "
    "and Development, System-Level Product Safety and EMC Testing, Manufacturing Support. Scalable electromechanical "
    "architectures and electromechanical mass-termination docking systems for advanced semiconductor testing. "
    "Bachelor of Science in Electrical Engineering and a strong grasp of electrical engineering principles.")
_PLANT_JD = ("Own the reliability of pumps and compressors across the site. Lead FMEA reviews, build preventive "
             "maintenance plans in the CMMS and support plant operations with root cause analysis on rotating equipment, "
             "working with maintenance planners and operators on every shift to raise availability across the whole of the plant.")
_SRE_JD = ("Run our production Kubernetes clusters on AWS. Terraform, Prometheus, Grafana, on call, SLOs and incident "
           "response. You write Python and Go, keep our CI/CD pipelines fast and own observability for every service, "
           "working with product teams to raise availability and to reduce the toil of the rotation.")
_ASIC_RELIABILITY_JD = ("Lead product qualification of our silicon. You plan stress tests, run failure analysis and report "
                        "lifetime data to customers, working with design, packaging and foundry teams on every new "
                        "product family, from early test chips through to high volume ramp at the fab, and you publish "
                        "the qualification report for every release.")


def test_the_two_teradyne_jobs_are_not_devops():
    assert tx.role_category("Power Infrastructure Engineer (Teradyne, Augora Hills, CA)", "Engineering", _TERADYNE_JD) == "other"
    assert tx.role_category("Senior Power Infrastructure Engineer (Teradyne, Agoura Hills, CA)", "Engineering", None) == "other"


def test_a_word_of_many_fields_is_settled_by_the_description():
    assert tx.role_category("Platform Engineer", None, _TERADYNE_JD) == "embedded_hw"
    assert tx.role_category("Reliability Engineer", None, _PLANT_JD) == "other"
    assert tx.role_category("Reliability Engineer", None, _ASIC_RELIABILITY_JD) == "other"
    assert tx.role_category("Reliability Engineer", None, _SRE_JD) == "devops_sre_cloud"
    assert tx.role_category("Senior Hardware Test and Reliability Engineer") == "embedded_hw"
    assert tx.role_category("Platform Engineer", None, _SRE_JD) == "devops_sre_cloud"


def test_no_description_keeps_the_titles_label():
    assert tx.role_category("Infrastructure Engineer") == "devops_sre_cloud"
    assert tx.role_category("Reliability Engineer", None, "Apply now.") == "devops_sre_cloud"
    assert tx.role_category("Platform Engineer", None, "") == "devops_sre_cloud"


def test_a_title_that_names_the_field_is_never_overruled():
    for title in ("DevOps Engineer", "Site Reliability Engineer", "Cloud Infrastructure Engineer", "SRE, Platform"):
        assert tx.role_category(title, None, _TERADYNE_JD) == "devops_sre_cloud", title
    assert tx.role_category("Senior System Software Engineer, SoC Power and Performance - O-RAN Infrastructure") == "software"


def test_power_products_stay_it():
    assert tx.role_category("Power Platform Engineer") != "other"
    assert tx.role_category("Power BI Developer") != "other"
    assert tx.role_category("Energy Infrastructure Software Engineer") == "software"


def test_words_that_mean_something_else_in_tech_are_not_field_terms():
    jd = ("Build the serving platform for our transformers and diffusion generators. Internal tooling, model rollout, "
          "and capacity planning for a London listed plc, working with researchers on every launch and with finance on "
          "the budget for the fleet, and owning the roadmap for the whole group across all of our regions.")
    assert tx.role_category("Platform Engineer", None, jd) == "devops_sre_cloud"


def test_a_reliability_title_whose_description_says_sre_stays_it():
    from services.jd_terms import physical_field
    filler = " We hire people who care about their teams and their customers." * 8
    sre = "You lead site reliability for our distributed systems." + filler
    assert physical_field(sre, "Engineering Manager - Reliability Engineering") is None
    assert physical_field("Our SRE group owns observability for the fleet." + filler, "Operations Engineering Manager, Fleet Reliability") is None
    # The same title without SRE words, or with plant words beside them, is still not an IT job.
    assert physical_field("You own Python tooling for reliability." + filler, "Reliability Engineer") == "physical"
    assert physical_field("Run FMEA on pumps, with an SRE mindset." + filler, "Reliability Engineer") == "physical"


def test_a_hardware_administrator_looks_after_machines():
    from services.jd_terms import physical_field
    filler = " We hire people who care about their teams and their customers." * 8
    assert physical_field("Maintain Linux hosts and networking." + filler, "Hardware Systems Administrator") is None
    assert physical_field("Maintain Linux hosts and networking." + filler, "Hardware Systems Engineer") == "electronics"
