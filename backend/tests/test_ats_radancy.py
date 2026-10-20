import asyncio
import json
from pathlib import Path

from scrapers.board_scraper import api_url, board_careers_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats"


def fixture(name):
    text = (FIX / name).read_text()
    return json.loads(text) if name.endswith(".json") else text


def scraper(ats, board, slug="atsco"):
    cls = build_scraper_class({"slug": slug, "company_name": "Ats Co", "ats": ats, "board": board, "careers_url": None})
    assert cls is not None
    return cls()


def test_radancy_board():
    assert api_url("radancy", "jobs.intuit.com") == "https://jobs.intuit.com/search-jobs/results"
    assert api_url("radancy", "jobs.walgreens.com/en") == "https://jobs.walgreens.com/en/search-jobs/results"
    assert api_url("radancy", "not a host") is None
    s = scraper("radancy", "jobs.intuit.com")
    job = s.parse_job({"job_id": "100138156416", "title": "Senior Money Specialist", "location": "Atlanta, Georgia",
                       "href": "/job/atlanta/senior-money-specialist/27595/100138156416"})
    assert job.job_url == "https://jobs.intuit.com/job/atlanta/senior-money-specialist/27595/100138156416"
