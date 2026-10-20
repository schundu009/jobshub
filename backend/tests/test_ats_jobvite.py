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

def test_jobvite_board_and_list():
    assert api_url("jobvite", "ninjaone") == "https://jobs.jobvite.com/ninjaone/jobs"
    assert api_url("jobvite", "a b") is None
    s = scraper("jobvite", "ninjaone")

    async def fetch_html(url, params=None):
        return fixture("jobvite/jobs.html")
    s.fetch_html = fetch_html
    result = asyncio.run(s.scrape())
    assert result.complete and len(result.jobs) == 2
    job = result.jobs[0]
    assert job.title == "Senior Data Analyst - Bandung, Indonesia"
    assert job.job_url == "https://jobs.jobvite.com/ninjaone/job/oi3ZAfwE"
    assert job.location == "Hybrid Remote, Bandung Wetan, Kota Bandung, Jawa Barat"
    assert job.department == "Accounting & Finance" and job.remote_type == "hybrid"
