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

def test_gem_job_posts():
    assert api_url("gem", "groq") == "https://api.gem.com/job_board/v0/groq/job_posts/"
    s = scraper("gem", "groq")

    async def fetch_json(url, **_):
        return fixture("gem/job_posts.json")
    s.fetch_json = fetch_json
    job = asyncio.run(s.scrape()).jobs[0]
    assert job.title == "Sr./Staff Forward Deployed Engineer"
    assert job.location == "San Francisco, United States"
    assert job.job_url.startswith("https://jobs.gem.com/groq/") and job.department == "Commercial Sales"
    assert job.remote_type == "on-site" and job.job_description
