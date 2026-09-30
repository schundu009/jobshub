"""Offline tests for the staffing-agency scrapers (contracts pipeline). No network:
every request is answered from recorded, PII-masked fixtures in
tests/fixtures/contracts/staffing/."""
import asyncio
import json
from datetime import datetime
from pathlib import Path

import pytest

from contracts.scrapers import load_all
from contracts.scrapers._base import (
    US_STATES,
    StaffingScraper,
    is_us_state,
    norm_period,
    parse_iso,
    parse_pay_text,
)
from contracts.scrapers.akkodis import AkkodisScraper
from contracts.scrapers.allegis import ActalentScraper, AerotekScraper, TEKsystemsScraper, pay_from_teaser
from contracts.scrapers.apex import ApexSystemsScraper, parse_apex_listing
from contracts.scrapers.collabera import CollaberaScraper
from contracts.scrapers.cybercoders import CyberCodersScraper
from contracts.scrapers.experis import ExperisScraper
from contracts.scrapers.insightglobal import InsightGlobalScraper
from contracts.scrapers.jobot import JobotScraper
from contracts.scrapers.judge import JudgeScraper
from contracts.scrapers.kforce import KforceScraper
from contracts.scrapers.motion import MotionRecruitmentScraper, parse_motion_page
from contracts.scrapers.randstad import RandstadScraper
from contracts.scrapers.roberthalf import RobertHalfScraper
from contracts.scrapers.yoh import YohScraper
from scrapers.base import ScrapedJob, ScraperConfig, ScraperType, UnexpectedResponseError
from scrapers.registry import ScraperRegistry

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts" / "staffing"
PII_MARKERS = ("recruiter", "contact", "email", "phone", "owner")


def responses(slug):
    return json.loads((FIXTURES / f"{slug}.json").read_text())["responses"]


def offline(scraper, replies):
    """Answer scraper._http from `replies` in order (the last one repeats); record calls."""
    calls = []
    replies = list(replies)

    async def fake_http(method, url, **kw):
        calls.append({"method": method, "url": url, **kw})
        return replies[min(len(calls), len(replies)) - 1]

    async def no_network():
        raise AssertionError("test tried to open a network session")

    scraper._http = fake_http
    scraper.get_session = no_network
    scraper.MIN_INTERVAL = 0
    return calls


def run_scrape(cls, slug=None, replies=None):
    scraper = cls()
    calls = offline(scraper, replies if replies is not None else responses(slug or cls.config.company_slug))
    result = asyncio.run(scraper.scrape())
    assert result.success
    return scraper, result.jobs, calls


def assert_common(jobs, agency, min_jobs=1):
    assert len(jobs) >= min_jobs
    ids = [j.external_job_id for j in jobs]
    assert len(ids) == len(set(ids))
    for j in jobs:
        assert isinstance(j, ScrapedJob)
        assert j.title and j.job_url.startswith("https://") and j.external_job_id
        assert j.extra["agency_name"] == agency
        for key in j.extra:
            assert not any(m in key.lower() for m in PII_MARKERS), key
        if j.pay_period:
            assert j.pay_period in ("hour", "day", "week", "month", "year")
            assert j.pay_rate_min and j.pay_rate_min > 0
            assert j.pay_rate_max is None or j.pay_rate_max >= j.pay_rate_min
    dated = [j.posted_date for j in jobs if j.posted_date]
    assert dated == sorted(dated, reverse=True)


# ------------------------------------------------------------------ helpers --

@pytest.mark.parametrize("text,expected", [
    ("$80-$85/hr W2 + Benefits", (80.0, 85.0, "hour")),
    ("70.00 - 75.00 | Per Hour", (70.0, 75.0, "hour")),
    (" $108,000.00 USD Annually - $150,000.00 USD Annually", (108000.0, 150000.0, "year")),
    ("$120k - $140k", (120000.0, 140000.0, "year")),
    ("$60.00 USD Hourly", (60.0, None, "hour")),
    ("Competitive", (None, None, None)),
    ("", (None, None, None)),
])
def test_parse_pay_text(text, expected):
    assert parse_pay_text(text) == expected


def test_norm_period_and_dates():
    assert norm_period("Hourly") == "hour"
    assert norm_period("PERHOUR") == "hour"
    assert norm_period("per year") == "year"
    assert norm_period("Annually") == "year"
    assert norm_period("weird") is None
    assert parse_iso("2026-09-02T22:30:29.561+0000") == datetime(2026, 9, 2, 22, 30, 29, 561000)
    assert parse_iso("2026-09-30T01:06:36.1Z") == datetime(2026, 9, 30, 1, 6, 36, 100000)
    assert parse_iso("1790678937000") == datetime(2026, 9, 29, 10, 48, 57)
    assert parse_iso(1790733309125).year == 2026
    assert parse_iso("09-29-2026") == datetime(2026, 9, 29)
    assert parse_iso("9/29/2026") == datetime(2026, 9, 29)
    assert parse_iso(None) is None and parse_iso("garbage") is None
    assert is_us_state("TX") and is_us_state("new york") and not is_us_state("ON")


def test_teaser_pay_extraction():
    teaser = "Location: Hybrid in Sunnyvale, CA . Compensation: $80-$85/hr W2 + Benefits..."
    assert pay_from_teaser(None, teaser) == (80.0, 85.0, "hour")
    assert pay_from_teaser("No pay here") == (None, None, None)


class _Dummy(StaffingScraper):
    config = ScraperConfig(company_slug="dummy-staffing", company_name="Dummy Staffing",
                           careers_url="https://example.com", scraper_type=ScraperType.HTTP)
    AGENCY_NAME = "Dummy Staffing"
    MAX_JOBS = 2

    async def fetch_raw(self):
        return []

    def parse_job(self, raw):
        return None


def test_make_job_and_finalize():
    s = _Dummy()
    j = s.make_job(title=" SRE ", location="", job_url="https://x/1", external_job_id=1,
                   employment_type_raw="Contract to Hire", pay_min="90", pay_max=70,
                   pay_period="Hourly", end_client="Confidential", skills=["go", "", 3])
    assert j.title == "SRE" and j.location == "United States"
    assert (j.pay_rate_min, j.pay_rate_max, j.pay_period) == (70.0, 90.0, "hour")
    assert j.employment_type == "contract" and j.employment_type_raw == "Contract to Hire"
    assert "end_client" not in j.extra and j.extra["skills"] == ["go"]
    y = s.make_job(title="Dev", location="Austin, TX", job_url="https://x/2", external_job_id="2",
                   pay_min=150000, pay_period="year", end_client="Acme Bank")
    assert (y.salary_min, y.salary_max) == (150000, 150000) and y.extra["end_client"] == "Acme Bank"
    # pay without a period is dropped rather than guessed
    z = s.make_job(title="QA", location="", job_url="https://x/3", external_job_id="3", pay_min=50)
    assert z.pay_rate_min is None and z.pay_period is None
    assert s.make_job(title="", location="", job_url="https://x", external_job_id="4") is None

    jobs = [s.make_job(title=f"T{i}", location="", job_url=f"https://x/{i}", external_job_id=str(i % 3),
                       posted_date=datetime(2026, 9, i + 1)) for i in range(5)]
    out = s.finalize(jobs)
    # first occurrence of each id wins, then newest first, capped at MAX_JOBS=2
    assert [j.external_job_id for j in out] == ["2", "1"]


# ------------------------------------------------------------- registration --

ENABLED = {
    "teksystems", "actalent", "roberthalf", "insightglobal", "kforce", "randstad", "akkodis",
    "judge", "experis", "yoh", "jobot", "cybercoders", "motionrecruitment", "collabera",
}


def _ensure_staffing_registered():
    """Other tests may call ScraperRegistry.reload(), which drops the staffing
    registrations (their modules are cached); re-run the decorators if so."""
    import importlib
    import pkgutil

    import contracts.scrapers as pkg

    load_all()
    if ENABLED <= set(ScraperRegistry.get_by_category("staffing")):
        return
    for info in pkgutil.iter_modules(pkg.__path__):
        if not info.name.startswith("_"):
            importlib.reload(importlib.import_module(f"contracts.scrapers.{info.name}"))


def test_registered_under_staffing_category():
    _ensure_staffing_registered()
    staffing = ScraperRegistry.get_by_category("staffing")
    assert ENABLED <= set(staffing)
    for slug in ENABLED:
        cls = staffing[slug]
        assert issubclass(cls, StaffingScraper)
        assert cls.config.scraper_type == ScraperType.HTTP
        assert ScraperRegistry.get_metadata(slug)["category"] == "staffing"
    disabled = ScraperRegistry.get_disabled()
    assert disabled["aerotek"]["category"] == "staffing"
    assert disabled["apexsystems"]["category"] == "staffing"
    assert "aerotek" not in staffing and "apexsystems" not in staffing


# ------------------------------------------------------------------ Phenom --

def test_teksystems_phenom():
    s, jobs, calls = run_scrape(TEKsystemsScraper)
    assert_common(jobs, "TEKsystems", min_jobs=15)
    assert calls[0]["url"].endswith("/us/en/search-results")
    widget = calls[1]
    assert widget["url"] == "https://careers.teksystems.com/widgets"
    assert widget["json_body"]["refNum"] == "TESYUS" and widget["json_body"]["ddoKey"] == "refineSearch"
    assert all(j.job_url.startswith("https://careers.teksystems.com/us/en/job/JP-") for j in jobs)
    assert {j.employment_type_raw for j in jobs} <= {"Contractor", "Full-time", "Contract to Hire", "Permanent"}
    assert any(j.extra.get("skills") for j in jobs)
    assert all(j.location for j in jobs)


def test_actalent_category_allowlist():
    s, jobs, _ = run_scrape(ActalentScraper)
    raw = responses("actalent")[1]["refineSearch"]["data"]["jobs"]
    allowed = [r for r in raw if r.get("category") in ActalentScraper.CATEGORIES]
    assert 0 < len(jobs) == len(allowed) < len(raw)
    assert all(j.department in ActalentScraper.CATEGORIES for j in jobs)


def test_aerotek_is_disabled_but_parses():
    assert AerotekScraper.config.enabled is False
    s = AerotekScraper()
    raw = responses("teksystems")[1]["refineSearch"]["data"]["jobs"][0]
    assert s.parse_job(dict(raw, country="Canada")) is None
    assert s.parse_job(raw).job_url.startswith("https://jobs.aerotek.com/us/en/job/")


# --------------------------------------------------------------- JSON APIs --

def test_roberthalf():
    s, jobs, calls = run_scrape(RobertHalfScraper)
    assert_common(jobs, "Robert Half", min_jobs=15)
    body = calls[0]["json_body"]
    assert body["lobid"] == ["RHT"] and body["sortby"] == "PUBLISHED_DATE_DESC"
    assert len(calls) == 1  # 'found' says everything came on page 1
    assert {j.employment_type_raw for j in jobs} <= {"Temp", "Perm", "Temp to Perm", "Fixed Term"}
    assert sum(1 for j in jobs if j.pay_period) >= len(jobs) // 2
    assert all(j.job_url.startswith("https://www.roberthalf.com/us/en/job/") for j in jobs)


def test_roberthalf_time_budget_stops_paging():
    scraper = RobertHalfScraper()
    page = responses("roberthalf")[0]
    page = dict(page, found="100000")
    calls = offline(scraper, [page])
    scraper.TIME_BUDGET_SECONDS = -1
    asyncio.run(scraper.scrape())
    assert len(calls) == 1


def test_insightglobal_filters_non_us():
    s, jobs, calls = run_scrape(InsightGlobalScraper)
    raw = responses("insightglobal")[0]["jobs"]
    assert_common(jobs, "Insight Global", min_jobs=10)
    assert len(jobs) < len(raw)  # Canadian postings (incl. the Toronto one) are dropped
    assert not any("Toronto" in j.location for j in jobs)
    assert all(j.location.rsplit(", ", 1)[-1] in US_STATES or j.location == "Remote" for j in jobs)
    assert calls[0]["params"]["sort"] == "postedDate,desc"
    assert all(j.job_url.startswith("https://insightglobal.com/jobs/") for j in jobs)
    assert all(j.pay_period == "hour" for j in jobs if j.pay_rate_min and j.pay_rate_min < 500)


def test_kforce():
    s, jobs, calls = run_scrape(KforceScraper)
    assert_common(jobs, "Kforce", min_jobs=15)
    assert calls[0]["headers"]["api-key"]
    assert calls[0]["json_body"]["filter"] == "Industry eq 'Technology'"
    assert {j.employment_type_raw for j in jobs} <= {"Contract", "Direct Hire"}
    assert all("#/detail/" in j.job_url for j in jobs)
    hourly = [j for j in jobs if j.employment_type_raw == "Contract" and j.pay_period]
    assert hourly and all(j.pay_period == "hour" for j in hourly)


def test_randstad():
    s, jobs, calls = run_scrape(RandstadScraper)
    assert_common(jobs, "Randstad", min_jobs=15)
    params = calls[0]["json_body"]["data"]["searchParams"]
    assert params["jobCategory"] == "Computer and Mathematical Occupations"
    assert any(j.extra.get("business_line") for j in jobs)
    assert all(j.job_url.startswith("https://www.randstadusa.com/jobs/") for j in jobs)


def test_randstad_second_page_payload():
    body = RandstadScraper()._payload(3)["data"]
    assert body["searchParams"]["page"] == "3"
    assert body["currentRoute"]["url"] == "/jobs/r-computer-and-mathematical-occupations/page-3/"


def test_akkodis_pages_by_offset():
    s, jobs, calls = run_scrape(AkkodisScraper)
    assert_common(jobs, "Akkodis", min_jobs=15)
    assert [c["json_body"]["range"] for c in calls[:2]] == [0, 10]
    assert all(j.job_url.startswith("https://www.akkodis.com/en-us/careers/jobs/") for j in jobs)
    assert all(j.job_url.endswith(j.external_job_id.lower()) for j in jobs)
    assert all(j.pay_period in (None, "hour", "year") for j in jobs)


def test_judge_double_encoded_json():
    s, jobs, calls = run_scrape(JudgeScraper)
    assert_common(jobs, "The Judge Group", min_jobs=15)
    assert calls[0]["json_body"]["payload"]["categories"] == ["InformationTechnology", "Engineering"]
    assert all(j.job_url.startswith("https://www.judge.com/jobs/details/") for j in jobs)
    assert {j.employment_type_raw for j in jobs} <= {"Contract", "Permanent"}


def test_judge_rejects_non_json():
    scraper = JudgeScraper()
    offline(scraper, ["<html>nope</html>"])
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(scraper.scrape())


def test_experis():
    s, jobs, calls = run_scrape(ExperisScraper)
    assert_common(jobs, "Experis", min_jobs=15)
    assert calls[0]["json_body"]["filter"]["offset"] == 0
    assert all(j.job_url.startswith("https://www.experis.com/en/job/") for j in jobs)
    assert all(j.job_description for j in jobs)


def test_yoh_feed():
    s, jobs, _ = run_scrape(YohScraper)
    assert_common(jobs, "Yoh", min_jobs=15)
    assert {j.employment_type_raw for j in jobs} <= {"Contract", "Contract To Hire", "Direct Hire"}
    assert all(j.job_url.startswith("https://jobs.yoh.com/job-details/") for j in jobs)


def test_jobot_consulting_only():
    s, jobs, calls = run_scrape(JobotScraper)
    assert_common(jobs, "Jobot", min_jobs=15)
    assert calls[0]["json_body"]["positionType"] == "consulting"
    assert {j.employment_type_raw for j in jobs} == {"consulting"}
    assert all(j.employment_type == "contract" for j in jobs)


def test_cybercoders_contract_bucket_and_end_client():
    s, jobs, calls = run_scrape(CyberCodersScraper)
    assert_common(jobs, "CyberCoders")
    assert calls[0]["params"]["termOption"] == "2"
    assert all(j.employment_type_raw == "Contract" for j in jobs)
    assert any(j.extra.get("end_client") for j in jobs)
    assert CyberCodersScraper.config.allow_empty


def test_empty_list_shape_is_an_error():
    scraper = KforceScraper()
    offline(scraper, [{"error": {"code": "Forbidden"}}])
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(scraper.scrape())


# -------------------------------------------------------------------- HTML --

def test_motion_rsc_payload():
    html = responses("motionrecruitment")[0]
    raw, total = parse_motion_page(html)
    assert len(raw) == 20 and total and total > 20
    s, jobs, calls = run_scrape(MotionRecruitmentScraper)
    assert_common(jobs, "Motion Recruitment", min_jobs=15)
    assert any(j.job_description and len(j.job_description) > 200 for j in jobs)
    assert not any((j.job_description or "").startswith("$") for j in jobs)
    assert {j.employment_type_raw for j in jobs} & {"Contract", "Direct Hire", "VMS/AE Temp"}
    assert all(j.job_url.startswith("https://motionrecruitment.com/tech-jobs/") for j in jobs)
    # page 2 is requested with ?start=20, then paging stops once no new ids arrive
    assert calls[1]["params"] == {"start": "20"} and len(calls) == 2


def test_collabera_cards():
    s, jobs, calls = run_scrape(CollaberaScraper)
    assert_common(jobs, "Collabera", min_jobs=5)
    assert all(j.job_url.startswith("https://www.collabera.com/job-description/?post=") for j in jobs)
    assert all(not j.location.endswith(", US") for j in jobs)
    assert any(j.employment_type_raw for j in jobs)
    assert any(j.pay_period == "hour" for j in jobs)
    assert "q" not in calls[0]["params"] and calls[1]["params"]["q"] == "2"


def test_apex_listing_parser():
    rows = parse_apex_listing(responses("apexsystems")[0])
    assert len(rows) == 25
    assert all(r["url"].startswith("https://www.apexsystems.com/job/") for r in rows)
    job = ApexSystemsScraper().parse_job(rows[0])
    assert job.external_job_id.endswith("_usa") and job.posted_date is not None
    assert job.employment_type_raw is None  # listing has no job type; not guessed
    assert ApexSystemsScraper.config.enabled is False
