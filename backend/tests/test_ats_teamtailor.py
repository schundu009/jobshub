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

def test_teamtailor_feed():
    assert api_url("teamtailor", "careers.strativgroup.com") == "https://careers.strativgroup.com/jobs.json"
    assert api_url("teamtailor", "strativ") is None
    s = scraper("teamtailor", "careers.strativgroup.com")

    async def fetch_json(url, **_):
        return fixture("teamtailor/jobs.json")
    s.fetch_json = fetch_json
    jobs = asyncio.run(s.scrape()).jobs
    assert jobs[0].title == "Recruitment Manager - Software Engineering (AI)"
    assert jobs[0].location == "Manchester, United Kingdom" and jobs[0].external_job_id == "7057328"
    assert jobs[0].job_url.startswith("https://careers.strativgroup.com/jobs/7057328-")
    assert jobs[1].location.startswith("Leeds, United Kingdom")
