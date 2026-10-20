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

def test_boostie_client_then_search():
    assert api_url("boostie", "jobs.theashgroup.com").endswith("getByBoardDomain?boardDomain=jobs.theashgroup.com")
    s = scraper("boostie", "jobs.theashgroup.com")
    seen = []

    async def fetch_json(url, method="GET", params=None, json_data=None, headers=None, **_):
        if "getByBoardDomain" in url:
            return {"data": {"externalId": "9b844fb7", "apiUrl": "https://api-us1.boostie.com/"}}
        seen.append((url, headers["X-Client-ExternalId"], json_data["currentPage"]))
        return fixture("boostie/search.json")
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert seen[0] == ("https://api-us1.boostie.com/api/boardJobPages/search", "9b844fb7", 1)
    job = result.jobs[0]
    assert job.title == "Hardware Engineer Mid." and job.external_job_id == "24696"
    assert job.job_url == "https://jobs.theashgroup.com/job/24696-hardware-engineer-mid-centennial-co"
    assert job.employment_type_raw == "Contract" and job.remote_type == "remote"
