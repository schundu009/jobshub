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

def test_monster_sts_search():
    assert api_url("monster-sts", "www.thefountaingroup.com") == \
        "https://www.thefountaingroup.com/api/requisitions/search"
    s = scraper("monster-sts", "www.thefountaingroup.com")

    async def fetch_html(url, params=None):
        assert params["defaultFeed"] == "true"
        return fixture("monster_sts/search.html") if params["page"] == "1" else ""
    s.fetch_html = fetch_html
    result = asyncio.run(s.scrape())
    job = result.jobs[0]
    assert job.title == "Administrative File Clerk" and job.external_job_id == "18385"
    assert job.job_url == "https://www.thefountaingroup.com/job/18385/administrative_file_clerk"
    assert (job.pay_rate_min, job.pay_rate_max, job.pay_period) == (41.0, 44.0, "hour")
    assert job.posted_date.year == 2026 and job.location
