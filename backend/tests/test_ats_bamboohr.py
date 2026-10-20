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

def test_bamboohr_list_and_detail():
    assert api_url("bamboohr", "wavelynx") == "https://wavelynx.bamboohr.com/careers/list"
    s = scraper("bamboohr", "wavelynx")

    async def fetch_json(url, **_):
        if url.endswith("/list"):
            return {"meta": {"totalCount": 1}, "result": [{"id": "71", "jobOpeningName": "Technical Support Representative",
                    "departmentLabel": "Product", "employmentStatusLabel": "Full-Time",
                    "location": {"city": "Broomfield", "state": "Colorado"}, "atsLocation": {}, "isRemote": None,
                    "locationType": "0"}]}
        assert url == "https://wavelynx.bamboohr.com/careers/71/detail"
        return {"result": {"jobOpening": {"description": "<p>Support.</p>", "datePosted": "2026-10-01",
                "location": {"city": "Broomfield", "state": "Colorado", "addressCountry": "United States"}}}}
    s.fetch_json = fetch_json
    job = asyncio.run(s.scrape()).jobs[0]
    assert job.location == "Broomfield, Colorado, United States" and job.job_description == "<p>Support.</p>"
    assert job.job_url == "https://wavelynx.bamboohr.com/careers/71" and job.remote_type == "on-site"
