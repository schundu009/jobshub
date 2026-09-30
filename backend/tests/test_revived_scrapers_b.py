"""Offline tests for scrapers revived on 2026-09-29: Revolut, Niantic, SAP, Dell, Meta (RippleMatch stays disabled)."""
import asyncio
import json

import pytest

from scrapers.base import UnexpectedResponseError
from scrapers.enterprise.sap import SAPScraper
from scrapers.finance.revolut import RevolutScraper
from scrapers.other.dell import DellScraper
from scrapers.other.niantic import NianticScraper
from scrapers.other.remaining_http import MetaHTTPScraper
from scrapers.registry import ScraperRegistry


# ─── Registry wiring ────────────────────────────────────────────────────────

@pytest.mark.parametrize("slug,cls", [
    ("revolut", RevolutScraper),
    ("niantic", NianticScraper),
    ("sap", SAPScraper),
    ("dell", DellScraper),
    ("meta", MetaHTTPScraper),
])
def test_revived_scrapers_are_registered(slug, cls):
    assert ScraperRegistry.get(slug) is cls
    assert cls.config.enabled and cls.config.disabled_reason is None
    assert slug not in ScraperRegistry.get_disabled()


def test_ripplematch_is_removed():
    assert ScraperRegistry.get("ripplematch") is None
    assert "ripplematch" not in ScraperRegistry.get_disabled()


@pytest.mark.parametrize("slug,fragment", [
    ("niantic", "api.ashbyhq.com/posting-api/job-board/niantic-spatial"),
    ("sap", "api.smartrecruiters.com/v1/companies/SAPITBusinessSysteme/postings"),
])
def test_moved_boards_point_at_new_ats(slug, fragment):
    assert fragment in ScraperRegistry.get(slug).API_URL


# ─── Revolut (positions embedded in the careers page) ───────────────────────

def _revolut_html(positions):
    data = {"props": {"pageProps": {"positions": positions, "isLanding": True}}, "page": "/careers/[[...slug]]"}
    return f'<html><body><script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script></body></html>'


REVOLUT_POSITIONS = [
    {"id": "6692237e-d90a-47ec-9a78-9b9699ff67bd", "text": "Visual Designer", "team": "Marketing & Comms",
     "description": "", "locations": [
         {"name": "Barcelona", "type": "office", "country": "Spain"},
         {"name": "Spain - Remote", "type": "remote", "country": "Spain"}]},
    {"id": "d40cf51d-7222-4064-9723-b1dc7eef849d", "text": "Graphic Designer (Brand)", "team": "Marketing & Comms",
     "locations": [{"name": "UK - Remote", "type": "remote", "country": "United Kingdom"}]},
    {"id": "", "text": "No id"},
]


def test_revolut_parses_next_data_positions():
    s = RevolutScraper()
    calls = []

    async def fetch_html(url, params=None):
        calls.append(url)
        return _revolut_html(REVOLUT_POSITIONS)
    s.fetch_html = fetch_html

    result = asyncio.run(s.scrape())
    assert calls == ["https://www.revolut.com/careers/"]
    assert result.success and result.jobs_found == 2
    first, second = result.jobs
    assert first.title == "Visual Designer"
    assert first.external_job_id == "6692237e-d90a-47ec-9a78-9b9699ff67bd"
    assert first.job_url == ("https://www.revolut.com/careers/position/"
                             "visual-designer-6692237e-d90a-47ec-9a78-9b9699ff67bd/")
    assert first.location == "Barcelona; Spain - Remote"
    assert first.department == "Marketing & Comms"
    assert first.remote_type is None  # mixed office/remote
    assert second.job_url.endswith("/graphic-designer-brand-d40cf51d-7222-4064-9723-b1dc7eef849d/")
    assert second.remote_type == "remote"


def test_revolut_bot_check_page_raises():
    s = RevolutScraper()
    with pytest.raises(UnexpectedResponseError):
        s.extract_positions("<html><title>Just a quick security check | Revolut</title></html>")


def test_revolut_sends_browser_headers():
    headers = {k.lower(): v for k, v in RevolutScraper.config.headers.items()}
    assert headers["sec-fetch-mode"] == "navigate"
    assert "Chrome/" in headers["user-agent"]


# ─── Meta (Relay GraphQL with LSD token) ────────────────────────────────────

META_PAGE = (
    '<html><script>["LSD",[],{"token":"AdTOKEN123"},323]</script>'
    '<script src="https://static.xx.fbcdn.net/rsrc.php/v4/a.js"></script>'
    '<script src="https://static.xx.fbcdn.net/rsrc.php/v4/b.js"></script></html>'
)
META_JOBS = {"data": {"job_search_with_featured_jobs_v2": {"all_jobs": [
    {"id": "1364785362399933", "title": "Product Quality Engineer", "locations": ["Singapore", "Taipei, Taiwan"],
     "teams": ["AI Infrastructure"], "sub_teams": ["Hardware"]},
    {"id": "42", "title": "Software Engineer", "locations": ["Remote, US"], "teams": [], "sub_teams": []},
    {"id": "", "title": "broken"},
], "featured_jobs": []}}}


def _stub_meta(s, query_responses, bundles=None):
    queries, fetched = [], []

    async def get_text(url, headers):
        fetched.append(url)
        if url == s.PAGE_URL:
            return META_PAGE
        return (bundles or {}).get(url, "")

    async def query(lsd, doc_id):
        queries.append((lsd, doc_id))
        return query_responses[doc_id]

    s._get_text = get_text
    s._query = query
    return queries, fetched


def test_meta_scrapes_all_jobs_with_lsd_token():
    s = MetaHTTPScraper()
    queries, _ = _stub_meta(s, {MetaHTTPScraper.DOC_ID: META_JOBS})
    result = asyncio.run(s.scrape())
    assert queries == [("AdTOKEN123", MetaHTTPScraper.DOC_ID)]
    assert result.success and result.jobs_found == 2
    job = result.jobs[0]
    assert job.job_url == "https://www.metacareers.com/profile/job_details/1364785362399933/"
    assert job.external_job_id == "1364785362399933"
    assert job.location == "Singapore; Taipei, Taiwan"
    assert job.department == "AI Infrastructure / Hardware"
    assert result.jobs[1].remote_type == "remote"


def test_meta_rediscovers_doc_id_from_bundles():
    s = MetaHTTPScraper()
    bundle = ('__d("CareersJobSearchResultsV2DataQuery_candidate_portalRelayOperation",[],'
              '(function(t,n,r,o,a,i){a.exports="999000111"}),null);')
    queries, fetched = _stub_meta(
        s,
        {MetaHTTPScraper.DOC_ID: {"errors": [{"message": "unknown doc_id"}]}, "999000111": META_JOBS},
        bundles={"https://static.xx.fbcdn.net/rsrc.php/v4/b.js": bundle},
    )
    result = asyncio.run(s.scrape())
    assert [q[1] for q in queries] == [MetaHTTPScraper.DOC_ID, "999000111"]
    assert "https://static.xx.fbcdn.net/rsrc.php/v4/b.js" in fetched
    assert result.jobs_found == 2


def test_meta_fails_loudly_without_lsd_or_new_doc_id():
    s = MetaHTTPScraper()
    _stub_meta(s, {MetaHTTPScraper.DOC_ID: {"errors": [{"message": "x"}]}})
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(s.scrape())

    s2 = MetaHTTPScraper()

    async def no_lsd(url, headers):
        return "<html>error</html>"
    s2._get_text = no_lsd
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(s2.scrape())


# ─── Niantic (Ashby), SAP (SmartRecruiters), Dell (Oracle HCM) ─────────────

def _with_json(scraper, payload, calls):
    async def fetch_json(url, method="GET", params=None, json_data=None, **_):
        calls.append((url, params))
        return payload
    scraper.fetch_json = fetch_json
    return scraper


def test_niantic_uses_ashby_board():
    calls = []
    s = _with_json(NianticScraper(), {"jobs": [
        {"id": "7d21", "title": "Technical Lead, Computer Vision", "location": "San Francisco, CA",
         "jobUrl": "https://jobs.ashbyhq.com/niantic-spatial/7d21", "department": "Engineering",
         "publishedAt": "2026-09-18T00:52:07.198Z", "isListed": True},
    ]}, calls)
    result = asyncio.run(s.scrape())
    assert calls[0][0].endswith("/job-board/niantic-spatial")
    job = result.jobs[0]
    assert job.job_url == "https://jobs.ashbyhq.com/niantic-spatial/7d21"
    assert job.department == "Engineering" and job.posted_date.year == 2026


def test_sap_uses_smartrecruiters_company():
    calls = []
    s = _with_json(SAPScraper(), {"totalFound": 1, "content": [
        {"id": "744000152551509", "name": "Technical Quality Manager-Services, South Korea",
         "refNumber": "REF2084F", "releasedDate": "2026-09-30T00:34:29.008Z",
         "location": {"city": "Seoul", "country": "kr"}, "department": {}},
    ]}, calls)
    result = asyncio.run(s.scrape())
    job = result.jobs[0]
    assert job.job_url == "https://jobs.smartrecruiters.com/SAPITBusinessSysteme/744000152551509"
    assert job.location == "Seoul" and job.external_job_id == "REF2084F"


def test_dell_uses_oracle_hcm_site():
    calls = []
    s = _with_json(DellScraper(), {"items": [{"TotalJobsCount": 1, "requisitionList": [
        {"Id": "296737", "Title": "Lead Specialist, Quality Control", "PrimaryLocation": "Malaysia",
         "PostedDate": "2026-09-30"},
    ]}]}, calls)
    result = asyncio.run(s.scrape())
    url, params = calls[0]
    assert url == "https://enterpriseplatform.dell.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    assert "siteNumber=CX_1001" in params["finder"]
    job = result.jobs[0]
    assert job.job_url == "https://enterpriseplatform.dell.com/hcmUI/CandidateExperience/en/sites/CX_1001/job/296737"
    assert job.location == "Malaysia" and job.posted_date.day == 30
    assert DellScraper.MAX_JOBS <= 1500
