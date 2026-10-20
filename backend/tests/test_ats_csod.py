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

def test_csod_token_then_search():
    assert api_url("csod", "cornerstone/2") == "https://cornerstone.csod.com/ux/ats/careersite/2/home?c=cornerstone"
    assert api_url("csod", "cornerstone") is None
    s = scraper("csod", "cornerstone/2")
    calls = []

    async def fetch_html(url, params=None):
        return fixture("csod/careersite.html")

    async def fetch_json(url, method="GET", json_data=None, headers=None, **_):
        calls.append((url, headers, json_data["careerSiteId"]))
        return fixture("csod/jobs.json")
    s.fetch_html, s.fetch_json = fetch_html, fetch_json
    result = asyncio.run(s.scrape())
    assert calls[0] == ("https://us-galaxy.api.csod.com/rec-job-search/external/jobs",
                        {"Authorization": "Bearer eyJ.test.token"}, 2)
    job = result.jobs[0]
    assert job.title == "Senior Deal Desk Analyst - Costa Rica" and job.location == "Heredia, CR"
    assert job.job_url == "https://cornerstone.csod.com/ux/ats/careersite/2/home/requisition/11638?c=cornerstone"
    assert job.posted_date.month == 10 and job.job_description
