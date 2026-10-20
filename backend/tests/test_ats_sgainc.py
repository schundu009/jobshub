"""SGA job service type (scrapers.ats.sgainc)."""
import asyncio
import json
from pathlib import Path

from scrapers.board_scraper import api_url, board_careers_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "sgainc"


def test_board_validation_and_parse():
    assert api_url("sgainc", "www.sgainc.com") == "https://www.sgainc.com/api/jobsvc/v1/jobs/recent-open-roles"
    assert board_careers_url("sgainc", "www.sgainc.com") == "https://www.sgainc.com/job-search"
    assert api_url("sgainc", "example.com") is None
    s = build_scraper_class({"slug": "sga", "company_name": "SGA", "ats": "sgainc", "board": "www.sgainc.com", "careers_url": None})()

    async def fetch_json(url, **_):
        return json.loads((FIX / "roles.json").read_text())
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    a, b = result.jobs
    assert a.title == "IT Infrastructure Engineer" and a.location == "Orlando, FL"
    assert a.job_url == "https://www.sgainc.com/job-search/26-02694" and a.remote_type == "hybrid"
    assert a.pay_rate_min is None and b.remote_type is None
