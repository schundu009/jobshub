"""Bullhorn OSCP public REST board type (scrapers.ats.bullhorn)."""
import asyncio
import json
from pathlib import Path

from scrapers.board_scraper import api_url, board_careers_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "bullhorn"
BOARD = "public-rest30/3vcpe1@cei.ai/jobs/#/jobs/"


def scraper(board=BOARD):
    cls = build_scraper_class({"slug": "bhco", "company_name": "BH Co", "ats": "bullhorn", "board": board, "careers_url": None})
    assert cls is not None
    return cls()


def test_board_validation_and_urls():
    assert api_url("bullhorn", "public-rest30/3vcpe1") is None  # needs the job page prefix
    assert api_url("bullhorn", "rest30/3vcpe1@cei.ai/jobs/") is None
    assert api_url("bullhorn", "public-rest30/bad token@cei.ai/") is None
    url = api_url("bullhorn", BOARD)
    assert url.startswith("https://public-rest30.bullhornstaffing.com/rest-services/3vcpe1/search/JobOrder?query=")
    assert "isOpen%3A1" in url and "count=200" in url and "start=0" in url
    assert board_careers_url("bullhorn", BOARD) == "https://cei.ai/jobs/"
    assert board_careers_url("bullhorn", "public-rest30/1XOC9@labur.com/career-portal/jobs/") == \
        "https://labur.com/career-portal/jobs/"


def test_scrape_and_parse():
    s = scraper()
    calls = []

    async def fetch_json(url, **_):
        calls.append(url)
        return json.loads((FIX / "search.json").read_text())
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert result.success and result.complete and len(result.jobs) == 3 and len(calls) == 1
    first, _, third = result.jobs
    assert first.title == "Senior Windows Server Engineer" and first.location == "Jersey City, New Jersey"
    assert first.job_url == "https://cei.ai/jobs/#/jobs/32932" and first.external_job_id == "32932"
    assert first.employment_type_raw == "Contract" and first.employment_type == "contract"
    # payRate empty: the posting's own "Pay:" line
    assert (first.pay_rate_min, first.pay_period) == (63.0, "hour")
    assert first.posted_date.year == 2026
    assert (third.pay_rate_min, third.pay_rate_max, third.pay_period) == (18.0, 18.0, "hour")
    assert third.location == "Dallas, TX"


def test_parse_without_city_uses_posting_location_and_salary():
    s = scraper("public-rest20/CRGTG0@asobbi.com/wp-content/plugins/bullhorn-oscp/#/jobs/")
    job = s.parse_job({"id": 965, "title": "Mechanical Design Engineer", "employmentType": "Permanent",
                       "address": {"city": None, "state": None, "countryID": 2359, "countryName": "United Kingdom"},
                       "salary": 80000.0, "salaryUnit": "", "payRate": 0.0,
                       "publicDescription": "<p>Location: London Head Office, with regular travel</p>"})
    assert job.location == "London Head Office"
    assert job.job_url == "https://asobbi.com/wp-content/plugins/bullhorn-oscp/#/jobs/965"
    assert (job.salary_min, job.pay_period) == (80000, "year")
    assert s.parse_job({"id": 1, "title": ""}) is None
