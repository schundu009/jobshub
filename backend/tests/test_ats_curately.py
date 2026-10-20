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

def test_curately_cards():
    assert api_url("curately", "careers.askconsulting.com") == "https://careers.askconsulting.com/api/v1/jobs/list"
    s = scraper("curately", "careers.askconsulting.com")
    pages = []

    async def fetch_html(url, params=None):
        pages.append(params["pageCount"])
        return fixture("curately/list.html") if params["pageCount"] == "1" else "\n\nempty_List\n"
    s.fetch_html = fetch_html
    result = asyncio.run(s.scrape())
    assert pages == ["1", "2"] and result.complete
    job = result.jobs[0]
    assert job.title == "Customer Engagement Manager III" and job.location == "Mountain View, CA, 94043"
    assert job.job_url == ("https://careers.curately.ai/careers/jobs/askconsulting/apply-jobs/132479/"
                           "Customer%20Engagement%20Manager%20III")
    assert job.remote_type == "hybrid" and job.pay_rate_min == 87.97 and job.pay_period == "hour"
    assert job.employment_type_raw == "Contract/Temp"
