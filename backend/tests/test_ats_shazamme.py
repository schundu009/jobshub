"""Shazamme job widget type (scrapers.ats.shazamme)."""
import asyncio
import json
from pathlib import Path

from scrapers.board_scraper import api_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "shazamme"
SITE = "08ee2cd8-7bbf-4fb2-b77a-14b746f4cb57"


def test_board_validation_and_urls():
    assert api_url("shazamme", SITE) == f"https://shazamme.io/job-results/{SITE}?"
    assert api_url("shazamme", "talentgroups") is None


def test_scrape_and_parse():
    s = build_scraper_class({"slug": "szco", "company_name": "SZ Co", "ats": "shazamme", "board": SITE, "careers_url": None})()

    async def request(method, url, read, **_):
        return json.loads((FIX / "results.json").read_text())
    s._request = request
    result = asyncio.run(s.scrape())
    assert result.success and len(result.jobs) == 2
    a, b = result.jobs
    assert a.title == "Epic Patient Experience Analyst" and a.location == "New Hyde Park, NY"
    assert a.job_url == "https://www.talentgroups.com/job-details/epic-patient-experience-analyst-in-other-jobs-1761572"
    assert a.employment_type_raw == "Contract" and a.pay_rate_min is None  # 0 - 0 is no rate
    assert (b.pay_rate_min, b.pay_rate_max, b.pay_period) == (26.0, 26.0, "hour")
