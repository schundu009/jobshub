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


def test_phenom_board():
    assert api_url("phenom", "careers.asurion.com/us/en") == "https://careers.asurion.com/us/en/search-results"
    assert api_url("phenom", "careers.asurion.com") is None  # the locale path is required
    assert api_url("phenom", "evil host/us/en") is None
    s = scraper("phenom", "www.yelp.careers/us/en")
    assert s.SITE_URL == "https://www.yelp.careers/us/en"
    job = s.parse_job({"jobId": "14002", "title": "Principal PM", "location": "San Francisco, California"})
    assert job.job_url == "https://www.yelp.careers/us/en/job/14002/Principal-PM"
    assert job.location == "San Francisco, California"
