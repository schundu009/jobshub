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

def test_keka_embedjobs():
    board = "relanto/02b7fe40-b031-4feb-9965-e44257ddd8e5"
    assert api_url("keka", board) == \
        "https://relanto.keka.com/careers/api/embedjobs/default/active/02b7fe40-b031-4feb-9965-e44257ddd8e5"
    assert api_url("keka", "relanto") is None
    s = scraper("keka", board)

    async def fetch_json(url, **_):
        return fixture("keka/embedjobs.json")
    s.fetch_json = fetch_json
    job = asyncio.run(s.scrape()).jobs[0]
    assert job.title == "Senior Software - Workato" and job.location == "Bengaluru, KA, IN"
    assert job.job_url == "https://relanto.keka.com/careers/jobdetails/144646"
    assert job.department == "Digital Transformation" and job.job_description
