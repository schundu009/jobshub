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

def test_workable_widget():
    assert api_url("workable", "innovaccer-analytics") == \
        "https://apply.workable.com/api/v1/widget/accounts/innovaccer-analytics"
    s = scraper("workable", "innovaccer-analytics")

    async def fetch_json(url, params=None, **_):
        assert params == {"details": "true"}
        return fixture("workable/widget.json")
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    job = result.jobs[0]
    assert job.job_url == "https://apply.workable.com/j/D1E02E0D44" and job.external_job_id == "D1E02E0D44"
    assert job.location == "Noida, Uttar Pradesh, India" and job.job_description.startswith("<p>")
    assert job.posted_date.year == 2026
