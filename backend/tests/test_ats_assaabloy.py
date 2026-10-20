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


def test_assaabloy_feed():
    assert api_url("assaabloy", "en").endswith("/job-openings/jobs.json")
    assert board_careers_url("assaabloy", "en") == "https://www.assaabloy.com/career/en/open-positions"
    assert api_url("assaabloy", "../x") is None
    s = scraper("assaabloy", "en")

    async def fetch_json(url, **_):
        return fixture("assaabloy/jobs.json")
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert result.complete and len(result.jobs) == 2
    job = result.jobs[0]
    assert job.title == "Service Tekniker - Norrland"
    assert job.location == "Skellefteå, Sweden; Umeå, Sweden"
    assert job.job_url == "https://www.assaabloy.com/career/en/open-positions/job.33718"
    assert job.posted_date.year == 2024 and job.department == "Construction"
