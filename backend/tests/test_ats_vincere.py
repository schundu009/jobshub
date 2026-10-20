"""Vincere quick job board type (scrapers.ats.vincere)."""
import asyncio
import json
from pathlib import Path

from scrapers.board_scraper import api_url, board_careers_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "vincere"


def test_board_validation_and_urls():
    assert api_url("vincere", "careers.edisonsmart.com") == "https://careers.edisonsmart.com/ajax/search-jobs"
    assert board_careers_url("vincere", "jobs.techire.ai") == "https://jobs.techire.ai/"
    assert api_url("vincere", "jobs.techire.ai/jobs") is None


def test_scrape_uses_page_csrf_token_and_parses():
    s = build_scraper_class({"slug": "vcco", "company_name": "VC Co", "ats": "vincere",
                             "board": "careers.edisonsmart.com", "careers_url": None})()
    calls = []

    async def request(method, url, read, **kwargs):
        calls.append((method, url, kwargs.get("headers")))
        if method == "GET":
            return (FIX / "page.html").read_text()
        return json.loads((FIX / "search.json").read_text())
    s._request = request
    result = asyncio.run(s.scrape())
    assert calls[0][:2] == ("GET", "https://careers.edisonsmart.com/")
    assert calls[1][0] == "POST" and calls[1][2]["X-CSRF-TOKEN"] == "tok123abc"
    assert result.success and result.complete and len(result.jobs) == 2
    a, b = result.jobs
    assert a.location == "Dallas, TX" and a.employment_type_raw == "Permanent, Full-time"
    assert a.job_url == "https://careers.edisonsmart.com/job/287886/technical-support-specialist"
    assert (a.salary_min, a.salary_max, a.pay_period) == (80000, 100000, "year")
    assert b.location == "Remote across the US or hybrid in San Francisco"
    assert (b.pay_rate_min, b.pay_period, b.employment_type) == (95.0, "hour", "contract")


def test_page_without_token_fails():
    s = build_scraper_class({"slug": "vcco2", "company_name": "VC Co", "ats": "vincere",
                             "board": "jobs.techire.ai", "careers_url": None})()

    async def request(method, url, read, **_):
        return "<html></html>"
    s._request = request
    assert not asyncio.run(s.scrape()).success
