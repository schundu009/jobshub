"""Offline tests for the iCIMS / SuccessFactors mixins and the repaired
Walmart, KeyBank, Redfin (Rocket Workday) and Lennar scrapers."""
import asyncio
from datetime import datetime

import pytest

from scrapers.base import UnexpectedResponseError
from scrapers.enterprise.icims_scrapers import (
    SchwabICIMSScraper,
    TollBrothersICIMSScraper,
    normalize_icims_location,
)
from scrapers.enterprise.misc_repaired_scrapers import (
    KeyBankWorkdayScraper,
    LennarCareersScraper,
    RedfinRocketWorkdayScraper,
    WalmartCareersScraper,
)
from scrapers.enterprise.successfactors_scrapers import ExxonMobilSuccessFactorsScraper
from scrapers.registry import ScraperRegistry


# ---------------------------------------------------------------------------
# iCIMS
# ---------------------------------------------------------------------------

def _icims_row(job_id, title, loc, category=None):
    cat = (
        f'<div class="iCIMS_JobHeaderTag"><dt class="iCIMS_JobHeaderField">Category</dt>'
        f'<dd class="iCIMS_JobHeaderData"><span>{category}</span></dd></div>'
        if category else ""
    )
    return f"""
    <div class="row">
      <div class="col-xs-6 header left"><span class="sr-only field-label">Job Locations</span>
        <span>{loc}</span></div>
      <div class="col-xs-6 header right"></div>
      <div class="col-xs-12 title">
        <a class="iCIMS_Anchor" href="https://career-acme.icims.com/jobs/{job_id}/slug/job?in_iframe=1"
           title="{job_id} - {title}"><span class="sr-only field-label">Job Posting Title</span><h3>{title}</h3></a>
      </div>
      <div class="col-xs-12 additionalFields"><dl class="iCIMS_JobHeaderGroup">
        <div class="iCIMS_JobHeaderTag"><dt class="iCIMS_JobHeaderField">Requisition ID</dt>
          <dd class="iCIMS_JobHeaderData"><span>2026-{job_id}</span></dd></div>{cat}
      </dl></div>
    </div>"""


def _icims_page(rows, page, total_pages):
    return f"""<html><body><ul class="container-fluid iCIMS_JobsTable">{''.join(rows)}</ul>
    <div class="iCIMS_Paging text-center"><div class="iCIMS_PagingBatch">
    <a class="selected" href="#"><span class="sr-only">Page</span> {page + 1}
    <span class="sr-only">of {total_pages} , Current Page</span></a></div></div></body></html>"""


def _with_html(scraper, pages, calls):
    async def fetch_html(url, params=None):
        calls.append((url, dict(params or {})))
        return pages(params or {})
    scraper.fetch_html = fetch_html
    return scraper


def test_icims_location_normalization():
    assert normalize_icims_location("US-IL-Chicago | US-TX-Austin") == "Chicago, IL, US; Austin, TX, US"
    assert normalize_icims_location("US-Remote") == "US-Remote"
    assert normalize_icims_location("") == ""


def test_icims_paginates_and_parses_rows():
    page_rows = {
        0: [_icims_row("101", "Engineer", "US-TX-Austin", "Technology"), _icims_row("102", "Analyst", "US-NY-New York")],
        1: [_icims_row("103", "Director", "US-CA-San Francisco | US-TX-Westlake")],
    }
    calls = []
    s = _with_html(SchwabICIMSScraper(), lambda p: _icims_page(page_rows[int(p["pr"])], int(p["pr"]), 2), calls)
    result = asyncio.run(s.scrape())
    assert [c[1]["pr"] for c in calls] == ["0", "1"]
    assert calls[0][0] == "https://career-schwab.icims.com/jobs/search"
    assert calls[0][1]["in_iframe"] == "1"
    assert result.jobs_found == 3
    job = result.jobs[0]
    assert job.title == "Engineer"
    assert job.external_job_id == "101"
    assert job.location == "Austin, TX, US"
    assert job.department == "Technology"
    assert job.job_url == "https://career-acme.icims.com/jobs/101/slug/job"  # ?in_iframe dropped
    assert result.jobs[2].location == "San Francisco, CA, US; Westlake, TX, US"


def test_icims_stops_when_page_repeats():
    rows = [_icims_row("1", "A", "US-TX-Austin")]
    calls = []
    # Pager missing -> unknown page count; the same page returned again must end the walk.
    s = _with_html(TollBrothersICIMSScraper(), lambda p: f'<ul class="iCIMS_JobsTable">{"".join(rows)}</ul>', calls)
    result = asyncio.run(s.scrape())
    assert result.jobs_found == 1
    assert len(calls) == 2


def test_icims_non_icims_page_raises():
    s = _with_html(SchwabICIMSScraper(), lambda p: "<html><body>Access denied</body></html>", [])
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(s.scrape())


# ---------------------------------------------------------------------------
# SuccessFactors
# ---------------------------------------------------------------------------

def _sf_row(job_id, title, loc, dept, date):
    return f"""
    <tr class="data-row">
      <td class="colTitle"><span class="jobTitle hidden-phone">
        <a href="/job/Houston-{title.replace(' ', '-')}-TX/{job_id}/" class="jobTitle-link">{title}</a></span>
        <div class="jobdetail-phone visible-phone"><span class="jobTitle visible-phone">
        <a href="/job/Houston-{title.replace(' ', '-')}-TX/{job_id}/" class="jobTitle-link">{title}</a></span></div></td>
      <td class="colLocation hidden-phone"><span class="jobLocation">{loc}</span></td>
      <td class="colDepartment hidden-phone"><span class="jobDepartment">{dept}</span></td>
      <td class="colDate hidden-phone"><span class="jobDate">{date}</span></td>
    </tr>"""


def test_successfactors_uses_total_and_startrow():
    total = 3
    rows = [_sf_row(str(1000 + i), f"Job {i}", "Houston, TX, US", "Engineering", "Sep 29, 2026") for i in range(total)]

    def page(p):
        start = int(p["startrow"])
        chunk = rows[start:start + 2]  # pretend page size 2
        return (f'<span class="paginationLabel">Results <b>{start + 1} – {start + len(chunk)}</b> of <b>{total}</b></span>'
                f'<table><tbody>{"".join(chunk)}</tbody></table>')

    calls = []
    s = _with_html(ExxonMobilSuccessFactorsScraper(), page, calls)
    result = asyncio.run(s.scrape())
    assert sorted(c[1]["startrow"] for c in calls) == ["0", "2"]
    assert calls[0][0] == "https://jobs.exxonmobil.com/search/"
    assert result.jobs_found == 3
    job = result.jobs[0]
    assert job.external_job_id == "1000"
    assert job.title == "Job 0"
    assert job.location == "Houston, TX, US"
    assert job.department == "Engineering"
    assert job.posted_date == datetime(2026, 9, 29)
    assert job.job_url == "https://jobs.exxonmobil.com/job/Houston-Job-0-TX/1000/"


def test_successfactors_non_sf_page_raises():
    s = _with_html(ExxonMobilSuccessFactorsScraper(), lambda p: "<html>maintenance</html>", [])
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(s.scrape())


# ---------------------------------------------------------------------------
# Workday: KeyBank + Redfin (Rocket tenant, company facet)
# ---------------------------------------------------------------------------

def test_redfin_sends_company_facet_and_builds_public_url(monkeypatch):
    calls = []

    async def http_fetch_json(self, url, method="GET", params=None, json_data=None, **_):
        calls.append((url, method, json_data))
        return {"total": 1, "jobPostings": [{
            "title": "Software Developer I", "externalPath": "/job/Seattle-WA/Software-Developer-I_R-1",
            "locationsText": "Seattle, WA", "postedOn": "Posted Today", "bulletFields": ["R-1"],
        }]}

    from scrapers.base import HTTPScraper
    # Patch the transport underneath WorkdayFacetMixin.fetch_json so the facet injection runs.
    monkeypatch.setattr(HTTPScraper, "fetch_json", http_fetch_json)
    result = asyncio.run(RedfinRocketWorkdayScraper().scrape())
    assert calls[0][2]["appliedFacets"] == {"hiringCompany": ["768c36a8181b10014e52c9cef6400000"]}
    assert calls[0][2]["limit"] <= 20
    assert result.jobs[0].job_url == (
        "https://quickenloans.wd5.myworkdayjobs.com/rocket_careers/job/Seattle-WA/Software-Developer-I_R-1"
    )


def test_keybank_site_url():
    s = KeyBankWorkdayScraper()
    job = s.parse_job({"title": "Teller", "externalPath": "/job/Troy-NY/Teller_R-9",
                       "locationsText": "Troy, NY", "bulletFields": ["R-9"]})
    assert job.job_url == "https://keybank.wd5.myworkdayjobs.com/External_Career_Site/job/Troy-NY/Teller_R-9"
    assert job.external_job_id == "R-9"


# ---------------------------------------------------------------------------
# Lennar
# ---------------------------------------------------------------------------

def _lennar_page(rows):
    trs = "".join(
        f'<tr><td class="job-title"><a href="https://careers.lennar.com/job/{i}/slug_{i}?change_lang=en">{t}</a></td>'
        f'<td class="job-location"><svg><title>address</title></svg> {loc}</td>'
        f'<td class="job-date">09/28/2026</td></tr>'
        for i, t, loc in rows
    )
    return f"<table><thead><tr><th class='job-title'>Job Title</th></tr></thead><tbody>{trs}</tbody></table>"


def test_lennar_pages_until_empty():
    pages = {1: [(1, "Construction Manager", "Nashville, TN")], 2: [(2, "Staff Accountant", "Miami, FL")], 3: []}
    calls = []
    s = _with_html(LennarCareersScraper(), lambda p: _lennar_page(pages[int(p["page"])]), calls)
    result = asyncio.run(s.scrape())
    assert [c[1]["page"] for c in calls] == ["1", "2", "3"]
    assert result.jobs_found == 2
    job = result.jobs[0]
    assert job.location == "Nashville, TN"  # svg "address" title stripped
    assert job.job_url == "https://careers.lennar.com/job/1/slug_1"
    assert job.external_job_id == "1"
    assert job.posted_date == datetime(2026, 9, 28)


# ---------------------------------------------------------------------------
# Walmart
# ---------------------------------------------------------------------------

def _walmart_job(jid, title="Senior Software Engineer"):
    return {"job_id": jid, "jobPostingTitle": title, "city": "SUNNYVALE", "state": "CA", "country": "US",
            "categories": ["Software Engineering"], "employmentTypes": ["Full time"],
            "minPay": 100000, "maxPay": 200000, "payFrequency": "Yearly",
            "jobPostingStartDate": 1788447267406, "additionalLocationCities": []}


def test_walmart_extract_jobs_handles_string_artifact_and_errors():
    import json
    data = {"data": {"jobSearchAssistant": {"tool_messages": [{"artifact": json.dumps({"jobs": [_walmart_job("R-1")]})}]}}}
    assert WalmartCareersScraper.extract_jobs(data)[0]["job_id"] == "R-1"
    with pytest.raises(UnexpectedResponseError):
        WalmartCareersScraper.extract_jobs({"errors": [{"message": "Something went wrong"}]})


def test_walmart_keyword_sweep_dedupes_and_uses_direct_search():
    calls = []

    async def fetch_json(url, method="GET", params=None, json_data=None, **_):
        if method == "GET":
            return {"status": "ok"}
        ctx = json_data["variables"]["chatRequest"]["context"]["job_search_context"]
        calls.append((ctx["refined_query"], ctx["job_page"], ctx["direct_search"]))
        jobs = [_walmart_job("R-1"), _walmart_job("R-2")] if ctx["job_page"] == 0 else []
        return {"data": {"jobSearchAssistant": {"tool_messages": [{"artifact": {"jobs": jobs}}]}}}

    s = WalmartCareersScraper()
    s.KEYWORDS = ["software engineer", "data"]
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert result.jobs_found == 2
    assert all(direct for _, _, direct in calls)
    assert {k for k, _, _ in calls} == {"software engineer", "data"}
    job = result.jobs[0]
    assert job.job_url == "https://careers.walmart.com/us/en/jobs/R-1"
    assert job.location == "Sunnyvale, CA, US"
    assert (job.salary_min, job.salary_max) == (100000, 200000)
    assert job.department == "Software Engineering"


def test_walmart_hourly_pay_not_reported_as_salary():
    job = WalmartCareersScraper().parse_job({**_walmart_job("CP-1-1", "Stocker"), "payFrequency": "Hourly",
                                             "minPay": 14, "maxPay": 27})
    assert job.salary_min is None and job.salary_max is None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_repaired_scrapers_are_registered_under_old_slugs():
    expected = {
        "schwab": SchwabICIMSScraper,
        "tollbrothers": TollBrothersICIMSScraper,
        "exxonmobil": ExxonMobilSuccessFactorsScraper,
        "keybank": KeyBankWorkdayScraper,
        "redfin": RedfinRocketWorkdayScraper,
        "lennar": LennarCareersScraper,
        "walmart": WalmartCareersScraper,
    }
    for slug, cls in expected.items():
        assert ScraperRegistry.get(slug) is cls
