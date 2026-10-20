"""SourceFlow site search type (scrapers.ats.sourceflow)."""
import asyncio
import json
from pathlib import Path

from scrapers.board_scraper import api_url, board_careers_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "sourceflow"


def test_board_validation_and_urls():
    assert api_url("sourceflow", "www.fueltalent.com/search-jobs") == "https://www.fueltalent.com/_sf/api/v1/jobs/search.json"
    assert board_careers_url("sourceflow", "www.glocap.com/jobs") == "https://www.glocap.com/jobs/"
    assert api_url("sourceflow", "www.fueltalent.com") is None
    assert api_url("sourceflow", "https://www.fueltalent.com/jobs") is None


def test_scrape_and_parse():
    cls = build_scraper_class({"slug": "sfco", "company_name": "SF Co", "ats": "sourceflow",
                               "board": "www.fueltalent.com/search-jobs", "careers_url": None})
    s = cls()
    bodies = []

    async def fetch_json(url, method="GET", json_data=None, **_):
        assert method == "POST"
        bodies.append(json_data)
        return json.loads((FIX / "search.json").read_text())
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert bodies == [{"job_search": {"query": "", "location": {}, "filters": {}, "offset": 0, "jobs_per_page": 50}}]
    assert result.success and result.complete and len(result.jobs) == 2
    a, b = result.jobs
    assert a.title == "Founding Engineer, Mobile & Web" and a.location == "Bellevue, Washington"
    assert a.job_url == "https://www.fueltalent.com/search-jobs/founding-engineer-mobile-web-5696/"
    assert (a.pay_rate_min, a.pay_rate_max, a.pay_period, a.salary_min) == (178000.0, 195000.0, "year", 178000)
    assert a.employment_type_raw == "Full Time"
    assert b.location == "Remote"  # no address; its "By Location" category says Remote
