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

def test_comeet_positions():
    board = "34.006/436150E150E0CA221B01D7A21B043621B0"
    assert api_url("comeet", board) == "https://www.comeet.co/careers-api/2.0/company/34.006/positions"
    assert api_url("comeet", "34.006") is None
    s = scraper("comeet", board)

    async def fetch_json(url, params=None, **_):
        assert params["token"] == "436150E150E0CA221B01D7A21B043621B0"
        return fixture("comeet/positions.json")
    s.fetch_json = fetch_json
    job = asyncio.run(s.scrape()).jobs[0]
    assert job.title == "Platform Engineer" and job.location == "United States (Remote)"
    assert job.job_url == "https://www.dariohealth.com/career-position/?uid=4E.07E"
    assert job.remote_type == "remote" and "<h3>Description</h3>" in job.job_description
