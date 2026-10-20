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

def test_oorwin_joblist():
    assert api_url("oorwin", "themesoftinc").startswith("https://api.oorwin.ai/api/v2/careers/getJobList")
    s = scraper("oorwin", "themesoftinc")
    bodies = []

    async def fetch_json(url, method="GET", json_data=None, **_):
        bodies.append(json_data)
        data = fixture("oorwin/joblist.json")
        data["data"]["list_details"]["last_page"] = 1
        return data
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert bodies[0]["sub_domain"] == "themesoftinc" and bodies[0]["page"] == 1
    job = result.jobs[0]
    assert job.location == "Newark, New Jersey, USA" and job.employment_type_raw == "Contractual"
    assert job.job_url == ("https://themesoftinc.oorwin.com/careers/index.html#/job/"
                           "74ca3335a695f9a800248609952972b7b661896e")
    assert job.remote_type == "on-site"
