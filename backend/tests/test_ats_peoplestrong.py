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

def test_peoplestrong_jobs():
    host = "larsentoubrocareers.peoplestrong.com"
    assert api_url("peoplestrong", host) == f"https://{host}/api/cp/rest/altone/cp/jobs/v1"
    assert api_url("peoplestrong", "evil.com") is None
    s = scraper("peoplestrong", host)
    urls = []

    async def fetch_json(url, method="GET", json_data=None, **_):
        urls.append(url)
        data = fixture("peoplestrong/jobs.json")
        data["totalRecords"] = 2
        return data
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert urls == [f"https://{host}/api/cp/rest/altone/cp/jobs/v1?offset=0&limit=99"] and result.complete
    job = result.jobs[0]
    assert job.title == "Site Architect" and job.location == "Ahmedabad, Gujarat, India"
    assert job.job_url == f"https://{host}/job/detail/LNT_SA_1900432"
