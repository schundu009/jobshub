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


from scrapers.ats.avature import location_from_slug


def test_avature_board():
    assert api_url("avature", "jobs.bmc.com/Careers") == "https://jobs.bmc.com/Careers/SearchJobs/"
    assert api_url("avature", "jobs.bmc.com") is None
    assert scraper("avature", "careers.radpartners.com/careersmarketplace").PORTAL_URL == \
        "https://careers.radpartners.com/careersmarketplace"


def test_avature_location_from_the_job_link_when_the_card_has_none():
    s = scraper("avature", "careers.radpartners.com/careersmarketplace")
    rows = s._extract_rows(fixture("avature/radpartners_search.html"))
    job = s.parse_job(rows[0])
    assert job.title == "Patient Service Representative | Belle Meade"
    assert job.location == "Nashville, Tennessee, United States"
    assert job.job_url.endswith("/JobDetail/Nashville-Tennessee-United-States-Patient-Service-Representative-Belle-Meade/20666")
    assert location_from_slug("https://x/JobDetail/Greensboro-North-Carolina-United-States-Day-Body-Radiologist/1",
                              "Day Body Radiologist") == "Greensboro, North Carolina, United States"
    assert location_from_slug("https://x/JobDetail/Engineer/1", "Engineer") == ""
