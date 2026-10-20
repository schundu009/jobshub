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

def test_ukg_ready_requisitions():
    board = "secure5.saashr.com/PayServ221004"
    assert api_url("ukg", board) == \
        "https://secure5.saashr.com/ta/rest/ui/recruitment/companies/%7CPayServ221004/job-requisitions"
    assert board_careers_url("ukg", board) == "https://secure5.saashr.com/ta/PayServ221004.careers?CareersSearch"
    assert api_url("ukg", "evil.com/PayServ221004") is None
    s = scraper("ukg", board)

    async def fetch_json(url, params=None, **_):
        return {"job_requisitions": [{"id": 51, "job_title": "Java Developer", "location": {"city": "Herndon",
                "state": "VA", "country": "USA"}, "employee_type": {"name": "Contract"},
                "job_description": "<p>Build.</p>", "base_pay_from": 60, "base_pay_to": 70,
                "base_pay_frequency": "Hourly"}], "_paging": {"offset": 1, "size": 200, "total": 1}}
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert result.complete
    job = result.jobs[0]
    assert job.location == "Herndon, VA, USA" and job.employment_type_raw == "Contract"
    assert job.job_url == "https://secure5.saashr.com/ta/PayServ221004.careers?ShowJob=51"
    assert (job.pay_rate_min, job.pay_rate_max, job.pay_period) == (60, 70, "hour")
