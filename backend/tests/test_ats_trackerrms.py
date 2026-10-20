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

def test_tracker_rms_publish_list():
    board = "evoportalus.tracker-rms.com/GoldenTechnology|goldenitinc.com/careers/job/"
    assert api_url("tracker-rms", board) == "https://evoportalus.tracker-rms.com/GoldenTechnology/jobs"
    assert board_careers_url("tracker-rms", board) == "https://goldenitinc.com/careers/job/"
    assert api_url("tracker-rms", "evil.com/GoldenTechnology") is None
    s = scraper("tracker-rms", board)

    async def fetch_html(url, params=None):
        assert params["joblinkuri"] == "https://goldenitinc.com/careers/job/"
        return fixture("trackerrms/publish.html")
    s.fetch_html = fetch_html
    job = asyncio.run(s.scrape()).jobs[0]
    assert job.title == "Cabin Design Engineer" and job.external_job_id == "23945"
    assert job.job_url == "https://goldenitinc.com/careers/job/?jobcode=23945"
    assert job.employment_type_raw == "Contract" and "aircraft cabins" in job.job_description
    assert job.posted_date.month == 8
