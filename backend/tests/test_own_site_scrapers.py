"""Offline tests for the scrapers of companies that list jobs on their OWN websites
(scrapers/custom/_own_site.py + one module per company; staffing firms under
contracts/scrapers/ on contracts/scrapers/_own_site.py).

No network: each scraper's saved listing response (tests/fixtures/own_sites/<slug>.json,
recorded 2026-10-20 and cut to a few postings) is parsed into ScrapedJobs, and the
paging / robots / budget plumbing is driven through a fake ``_http``."""
import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest

import contracts.scrapers as staffing_pkg
from contracts.scrapers._base import StaffingScraper
from contracts.scrapers._own_site import OwnSiteStaffingScraper, stable_id
from scrapers.base import ScrapedJob, ScraperType
from scrapers.custom import _own_site as own
from scrapers.registry import ScraperRegistry

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "own_sites"

# slug -> (title, location, job_url, external_job_id) of the first posting in the fixture
FIRST = {
    "aloissolutions": ("IBM OpenPages Workflow Expert", "Australia", "https://aloissolutions.com/opportunities/job/APAC/z5G7h3l6a1kMvyS65NP3cwGkp6VKTzqJva3fWPA66r8=", "JPC4144"),
    "amd": ("Sr. Staff Physical Design Engineer", "VANCOUVER, Canada", "https://careers.amd.com/careers-home/jobs/93495", "93495"),
    "compunnel": ("Senior Application Analyst", "Sherwood Park, Alberta", "https://staffline.compunnel.com/Support/UploadResume?JobId=wCfDBy331WZFEidDigr4XQ%3d%3d&Source=4414&EntityGroup=2321", "6009035"),
    "discoverinternational": ("Head of Packaging & Inspection Engineering", "Germany", "https://www.discoverinternational.com/jobs/1693/head-of-packaging-inspection-engineering", "1693"),
    "doghouse": ("Site Reliability Engineer", "United States", "https://www.doghouse.nl/job/site-reliability-engineer", "CgosmpfuS6ORNL413PjgRw"),
    "eliosai": ("Forward Deployed Engineer (AI) — Brazil (Remote)", "Brazil (Remote)", "https://eliosai.com/browse-jobs/forward-deployed-engineer-ai-brazil-remote", "1f1c71c3-f0cd-6910-b0a7-73a0f785662e"),
    "emapta": ("Estimating Assistant", "Philippines (Remote)", "https://careers.emapta.com/JobListing?JobId=01a1585b-9910-7936-b223-f84b7815ab7e", "JOB-1792483758938499"),
    "fullstacklabs": ("Agentic Elixir Engineer - Remote - Latin America", "Costa Rica (Remote)", "https://talent.fullstack.com/jobs/000b0241-7798-4f45-ab39-606475da430a", "000b0241-7798-4f45-ab39-606475da430a"),
    "github": ("Staff Software Engineer, Enterprise Platform", "United States (Remote)", "https://www.github.careers/careers-home/jobs/6126", "6126"),
    "gspann": ("Azure Cloud Native Architect", "Gurugram / Hyderabad, India", "https://careers.gspann.com/jobs/open-positions/infrastructure-architects", "infrastructure-architects"),
    "gurulink": ("Technical Program Manager", "REMOTE / Nashville, Tennessee - USA", "https://app.gurulink.ca/jobview.asp?JobID=7936", "7936"),
    "holisticpartners": ("Salesforce Forward Deployed Engineer", "United States (Remote)", "https://holistic-partners.com/find-a-job/job-details?job_id=z5G7h3l6a1kMvyS65NP3c2DJOcEmJUd6uwA15MSFDBs%3D&job_code=JPC+-+33716", "JPC - 33716"),
    "htcglobal": ("Data Engineer II – Google Cloud Platform (GCP) & AI", "Dearborn, MI, United States", "https://www.htcinc.com/job-detail/?jobcode=245752", "245752"),
    "impaxrecruitment": ("Head of Research", "Not specified", "https://www.impaxrecruitment.com/job/head-of-research", "head-of-research"),
    "infojini": ("HMS Analyst - 737400 - RD", "Raleigh, North Carolina", "https://talentdome.infojiniconsulting.com/careers/389ff815-e886-4181-9365-f069d11a25c5/In18169023/details", "In18169023"),
    "infosys": ("Cloud Engineer (AWS/Azure/GCP with Kubernates)", "Bangalore, India", "https://career.infosys.com/jobdesc?jobReferenceCode=INFSYS-EXTERNAL-255505&sourceId=1", "INFSYS-EXTERNAL-255505"),
    "innovasolutions": ("Quality Assurance Analyst - Wire Payments", "Charlotte, NC", "https://jobsusa.innovasolutions.com/job/quality-assurance-analyst-wire-payments-in-charlotte-nc-7272019", "7272019"),
    "intelliswift": ("IT Program Manager", "Newark, CA", "https://www.intelliswift.com/current-opening/it-program-manager", "it-program-manager"),
    "lumenalta": ("Senior AI Engineer", "Remote", "https://lumenalta.com/jobs/ai-engineer-ai-engineer-551", "68dee35f8c9481db144ea376"),
    "manpower": ("Stand Up Forklift Operators", "Franklin, WI", "https://www.manpower.com/en-us/job/transportation/stand-up-forklift-operators-/5894367", "5894367"),
    "mastech": ("OpenShift Engineer", "Dallas, TX (Remote)", "https://jobs.mastech.com/client/Job/openshift-engineer-in-Dallas-TX?jobNum=24086354&jc=300358", "24086354"),
    "meytier": ("Onsite Client Contact & Delivery Partner – Data Center Exit Program", "Berkeley Heights / New Jersey / Alpharetta", "https://meytier.com/job/3581-onsite-client-contact-delivery-partner-data-center-exit-program", "3581"),
    "michaelpage": ("Warehouse & Logistics Manager", "Carol Stream, Illinois", "https://www.michaelpage.com/job-detail/warehouse-logistics-manager/ref/jn-092026-7114848", "jn-092026-7114848"),
    "micro1": ("Certified Inpatient Coder", "Remote", "https://jobs.micro1.ai/post/345daaa5-4cbe-4af3-af6f-4e27382d6d41", "345daaa5-4cbe-4af3-af6f-4e27382d6d41"),
    "mobileprogramming": ("Senior QA Engineer", "Bangalore, India", "https://www.mobileprogramming.com/careers#senior-qa-engineer", "dd24deedda3decd0"),
    "opensystemstech": ("AWS Sr. Sales Account Executive", "Chicago, IL", "https://www.opensystemstech.com/job/2581/aws_sr_sales_account_executive", "2581"),
    "opstalent": ("Customer Success Specialist with English", "Wrocław, Poland", "https://opstalent.com/career#offer-1", "1"),
    "osiengineering": ("Aerospace Engineering Technician in Southern CA", "Southern, CA", "https://osiengineering.com/job-details/?jobid=2087", "2087"),
    "paragonitpros": ("Application Architect", "Des Moines, IA", "https://info.paragonitpros.com/applicationarchitect", "applicationarchitect"),
    "perinternational": ("Staff/Senior Staff GPU Engineer - Shader RTL & Microarchitecture", "California", "https://www.per-international.com/jobs/staffsenior-staff-gpu-engineer-shader-rtl-microarchitecture-aba2d538-f092-44a0-8355-3bc57de90ada", "aba2d538-f092-44a0-8355-3bc57de90ada"),
    "programmersio": ("Senior Accounts Executive", "Jaipur", "https://programmers.io/job-opening-detail/?jobId=317", "317"),
    "sciencecorp": ("Mechanical Assembly Technician", "Alameda, CA, United States", "https://science.xyz/careers/mechanical-assembly-technician-165", "165"),
    "spectraforce": ("Clinical Application Specialist II", "United States (Remote)", "https://spectraforce.com/careers/jobs/clinical-application-specialist-ii-remote-usa-503987", "503987"),
    "tek1it": ("DevOps Engineer", "Hyderabad, India", "https://www.tek1it.com/careers#job-1", "1"),
    "tenthrevolution": ("Software Developer", "Toulouse, France", "https://www.tenthrevolution.com/job/software-developer-4/", "a0MP900000AM3G1MAL"),
    "welovesalt": ("Senior Data Analyst", "Cape Town, South Africa", "https://welovesalt.com/jobs/senior-data-analyst-715653", "715653"),
    "winwire": ("Project Manager / Sr Project Manager – App Dev", "Hyderabad or Bengaluru, India", "https://www.winwire.com/jobs/project-manager-application-development/", "project-manager-application-development"),
}
CUSTOM = {"amd", "github", "eliosai", "sciencecorp", "winwire", "emapta", "infosys", "lumenalta", "programmersio",
          "htcglobal", "gspann", "fullstacklabs", "discoverinternational", "doghouse", "tenthrevolution",
          "impaxrecruitment", "michaelpage", "welovesalt", "meytier", "perinternational", "gurulink"}
STAFFING = {"opstalent", "opensystemstech", "compunnel", "brezq", "micro1", "spectraforce", "intelliswift",
            "holisticpartners", "innovasolutions", "paragonitpros", "mobileprogramming", "mastech", "tek1it",
            "aloissolutions", "infojini", "manpower", "osiengineering"}


def _registered() -> dict:
    """slug -> class for every own-site scraper (re-running the decorators if another
    test called ScraperRegistry.reload(), which drops the staffing registrations)."""
    import importlib
    ScraperRegistry._ensure_loaded()
    staffing_pkg.load_all()
    found = {s: ScraperRegistry._scrapers.get(s) for s in CUSTOM | STAFFING}
    for slug, cls in found.items():
        if cls is None:
            pkg = "scrapers.custom" if slug in CUSTOM else "contracts.scrapers"
            module = {"fullstacklabs": "fullstack"}.get(slug, slug)
            importlib.reload(importlib.import_module(f"{pkg}.{module}"))
            found[slug] = ScraperRegistry._scrapers.get(slug)
    return found


@pytest.fixture(scope="module")
def classes():
    return _registered()


def fixture(name: str):
    return json.loads((FIXTURES / f"{name}.json").read_text())["payload"]


def parse_fixture(cls):
    scraper = cls()
    if isinstance(scraper, StaffingScraper):
        scraper.IT_ONLY = False
    items = scraper.listing_items(fixture(cls.config.company_slug))
    return scraper, [j for j in (scraper.parse_job(i) for i in items) if j]


def offline(scraper, handler):
    """Answer scraper._http with handler(method, url, **kw); record the calls; allow robots."""
    calls = []

    async def fake_http(method, url, **kw):
        calls.append({"method": method, "url": url, **kw})
        return handler(method, url, **kw)

    async def robots_ok(url):
        return True

    async def no_network():
        raise AssertionError("test tried to open a network session")

    scraper._http = fake_http
    scraper._robots_ok = robots_ok
    scraper.get_session = no_network
    scraper.MIN_INTERVAL = 0
    return calls


# ---------------------------------------------------------------- registration --

def test_every_scraper_registered_in_its_category(classes):
    custom = set(ScraperRegistry.get_by_category("custom"))
    staffing = set(ScraperRegistry.get_by_category("staffing"))
    for slug, cls in classes.items():
        assert cls is not None, slug
        assert cls.config.company_slug == slug
        assert cls.config.scraper_type == ScraperType.HTTP
        if slug in CUSTOM:
            assert slug in custom and issubclass(cls, own.OwnSiteScraper), slug
        else:
            assert slug in staffing and issubclass(cls, OwnSiteStaffingScraper), slug
            assert cls.IT_ONLY, slug


def test_every_scraper_has_a_fixture(classes):
    for slug in classes:
        assert (FIXTURES / f"{slug}.json").exists(), slug


# ------------------------------------------------------------- parse fixtures --

@pytest.mark.parametrize("slug", sorted(FIRST))
def test_fixture_parses_into_jobs(classes, slug):
    scraper, jobs = parse_fixture(classes[slug])
    assert jobs, slug
    for job in jobs:
        assert isinstance(job, ScrapedJob)
        assert job.title and job.title == job.title.strip()
        assert job.location
        assert job.job_url.startswith("https://")
        assert job.external_job_id
    assert len({j.external_job_id for j in jobs}) == len(jobs), "external ids are unique"
    title, location, url, ext = FIRST[slug]
    first = jobs[0]
    assert (first.title, first.location, first.job_url, first.external_job_id) == (title, location, url, ext)


def test_ids_are_stable_across_parses(classes):
    for slug in ("mobileprogramming", "tek1it", "gspann", "infosys"):
        _, a = parse_fixture(classes[slug])
        _, b = parse_fixture(classes[slug])
        assert [j.external_job_id for j in a] == [j.external_job_id for j in b]


def test_descriptions_dates_and_contract_fields(classes):
    _, amd = parse_fixture(classes["amd"])
    assert amd[0].job_description and "<" not in amd[0].job_description[:200]
    assert amd[0].posted_date == datetime(2026, 10, 20, 15, 10)
    _, infosys = parse_fixture(classes["infosys"])
    assert "Responsibilities:" in infosys[0].job_description
    _, mastech = parse_fixture(classes["mastech"])
    m = mastech[0]
    assert (m.pay_rate_min, m.pay_rate_max, m.pay_period) == (70.0, 70.0, "hour")
    assert m.employment_type == "contract" and m.extra["agency_name"] == "Mastech Digital"
    _, holistic = parse_fixture(classes["holisticpartners"])
    h = holistic[0]
    assert h.employment_type_raw == "C2C" and h.pay_period == "hour" and h.pay_rate_max == 80.0
    assert not any(k in json.dumps(h.extra) for k in ("recruiter", "posted_by"))
    _, compunnel = parse_fixture(classes["compunnel"])
    assert compunnel[0].extra.get("end_client")
    assert "Recruiter" not in json.dumps(compunnel[0].extra)
    _, doghouse = parse_fixture(classes["doghouse"])
    assert "doghouse-recruitment.nl" not in json.dumps([j.extra for j in doghouse])  # no recruiter contacts


# -------------------------------------------------------------------- helpers --

@pytest.mark.parametrize("value,expected", [
    ("2026-10-20T15:10:00+0000", datetime(2026, 10, 20, 15, 10)),
    ("2026-10-20T08:09:20.091Z", datetime(2026, 10, 20, 8, 9, 20, 91000)),
    ("2026-10-20 10:49:17", datetime(2026, 10, 20, 10, 49, 17)),
    ("/Date(1791824156137)/", datetime(2026, 10, 12, 16, 55, 56, 137000)),
    ("10/20/2026", datetime(2026, 10, 20)),
    ("October 13, 2026", datetime(2026, 10, 13)),
    ("", None), ("soon", None),
])
def test_parse_when(value, expected):
    assert own.parse_when(value) == expected


def test_jsonld_postings_and_location():
    payload = fixture("brezq_detail")
    postings = own.jsonld_postings(payload)
    assert postings and postings[0]["title"] == "Principal Cloud Architect"
    graph = '<script type="application/ld+json">{"@graph": [{"@type": "Organization"}, {"@type": "JobPosting", ' \
            '"title": "X", "jobLocation": {"address": {"addressLocality": "Austin", "addressRegion": "TX", ' \
            '"addressCountry": "US"}}}]}</script>'
    found = own.jsonld_postings(graph)
    assert [p["title"] for p in found] == ["X"]
    assert own.jsonld_location(found[0]) == "Austin, TX, US"


def test_stable_id_ignores_case_and_punctuation():
    assert stable_id("Data Scientist", "Pune") == stable_id("data scientist ", "PUNE")
    assert stable_id("Data Scientist", "Pune") != stable_id("Data Scientist", "Noida")


# ------------------------------------------------------- scrape loops, offline --

def test_jibe_pages_until_total(classes):
    page1 = fixture("github")
    s = classes["github"]()
    s.PAGE_LIMIT = 2

    def handler(method, url, params=None, **kw):
        jobs = page1["jobs"][:2] if params["page"] == 1 else page1["jobs"][2:3]
        return {"jobs": jobs, "totalCount": 3}

    calls = offline(s, handler)
    result = asyncio.run(s.scrape())
    assert result.success and result.complete and len(result.jobs) == 3
    assert [c["params"]["page"] for c in calls] == [1, 2]
    assert calls[0]["url"] == "https://www.github.careers/api/jobs"


def test_job_cap_marks_result_incomplete(classes):
    page = fixture("amd")
    s = classes["amd"]()
    s.MAX_JOBS = 2
    offline(s, lambda m, u, params=None, **kw: {"jobs": page["jobs"] if params["page"] == 1 else [], "totalCount": 1283})
    result = asyncio.run(s.scrape())
    assert result.success and not result.complete and len(result.jobs) == 2


def test_html_page_disallowed_by_robots_is_not_read(classes):
    s = classes["sciencecorp"]()
    calls = offline(s, lambda *a, **k: fixture("sciencecorp"))

    async def deny(url):
        return False

    s._robots_ok = deny
    # _http itself enforces robots; call the real one with a session that must not open
    s._http = own.OwnSiteScraper._http.__get__(s)
    result = asyncio.run(s.scrape())
    assert not result.success and "robots.txt" in result.error_message
    assert calls == []


def test_staffing_html_page_disallowed_by_robots(classes):
    s = classes["osiengineering"]()
    offline(s, lambda *a, **k: fixture("osiengineering"))

    async def deny(url):
        return False

    s._robots_ok = deny
    s._http = OwnSiteStaffingScraper._http.__get__(s)
    result = asyncio.run(s.scrape())
    assert not result.success and "robots.txt" in result.error_message


def test_staffing_it_filter_drops_non_it(classes):
    s = classes["opstalent"]()
    offline(s, lambda *a, **k: {"data": {"jobOfferSearch": [
        {"id": "1", "title": {"title_en": "Customer Success Specialist with English"}, "jobCategory": {"name_en": "CX"},
         "location": {"description_en": "Wroclaw, Poland"}},
        {"id": "14", "title": {"title_en": "D365 F&O Solution Architect"}, "jobCategory": {"name_en": "Technology"},
         "location": {"description_en": "Wroclaw, Poland / Hybrid"}},
    ]}})
    result = asyncio.run(s.scrape())
    assert [j.title for j in result.jobs] == ["D365 F&O Solution Architect"]
    assert s.it_dropped == 1


def test_fullstack_reads_a_rotating_slice_within_the_rate_limit(classes):
    s = classes["fullstacklabs"]()
    page = fixture("fullstacklabs")

    def handler(method, url, params=None, **kw):
        n = params["page"]
        items = [dict(page["data"][0], id=f"p{n}-{i}") for i in range(3)]
        return {"data": items, "meta": {"pageCount": 80, "hasNextPage": n < 80}}

    calls = offline(s, handler)
    result = asyncio.run(s.scrape())
    pages = [c["params"]["page"] for c in calls]
    assert pages[0] == 1 and len(pages) == s.PAGES_PER_RUN and len(set(pages)) == len(pages)
    assert all(c["params"]["take"] == 30 for c in calls)
    assert not result.complete and len(result.jobs) == 3 * s.PAGES_PER_RUN


def test_emapta_reads_version_tokens_from_the_app(classes):
    s = classes["emapta"]()
    script = ('return controller.callDataAction("DataActionGetJobs", '
              '"screenservices/Careers_UI/MainFlow/JobCards_LandingPage/DataActionGetJobs", "API123", function')

    def handler(method, url, json_body=None, headers=None, **kw):
        if url.endswith("moduleversioninfo"):
            return {"versionToken": "MOD456"}
        if url.endswith(".mvc.js"):
            return script
        assert json_body["versionInfo"] == {"moduleVersion": "MOD456", "apiVersion": "API123"}
        assert headers["X-CSRFToken"]
        return fixture("emapta")

    offline(s, handler)
    result = asyncio.run(s.scrape())
    assert result.success and len(result.jobs) == 3


def test_doghouse_sends_the_body_as_text_plain(classes):
    s = classes["doghouse"]()
    calls = offline(s, lambda *a, **k: {"metadata": {"count": 3}, "data": fixture("doghouse")["data"]})
    asyncio.run(s.scrape())
    assert calls[0]["headers"]["Content-Type"].startswith("text/plain")
    assert json.loads(calls[0]["data"]) == {"offset": 0, "size": 100, "tags": []}


def test_brezq_reads_jsonld_from_each_role_page(classes):
    s = classes["brezq"]()
    listing, detail = fixture("brezq"), fixture("brezq_detail")
    calls = offline(s, lambda m, url, **k: listing if url.endswith("/careers") else detail)
    result = asyncio.run(s.scrape())
    assert result.success and result.jobs
    job = result.jobs[0]
    assert job.title == "Principal Cloud Architect" and job.location == "London / Remote"
    assert job.job_description and job.posted_date == datetime(2026, 3, 1)
    assert len(calls) == 1 + len(s.listing_items(listing))


def test_impax_detail_fields():
    from scrapers.custom.impaxrecruitment import detail_fields
    fields = detail_fields(fixture("impaxrecruitment_detail"))
    assert fields["Location"] == "San Francisco"
    assert fields["Salary"].startswith("$300k")
    assert "foundation models" in fields["Job Description"]


def test_salt_stops_at_the_404_after_the_last_page(classes):
    import aiohttp
    s = classes["welovesalt"]()
    page = fixture("welovesalt")

    def handler(method, url, **kw):
        if url.endswith("/page/3"):
            raise aiohttp.ClientResponseError(None, (), status=404, message="Not Found")
        n = 1 if url.endswith("/jobs") else int(url.rsplit("/", 1)[-1])
        return page.replace("715653", f"9{n}9653").replace("715652", f"9{n}9652")

    calls = offline(s, handler)
    result = asyncio.run(s.scrape())
    assert result.success and result.complete
    assert [c["url"].rsplit("/", 1)[-1] for c in calls] == ["jobs", "2", "3"]
