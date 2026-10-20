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

def test_recruitee_offers():
    assert api_url("recruitee", "infoprolearning") == "https://infoprolearning.recruitee.com/api/offers/"
    s = scraper("recruitee", "infoprolearning")

    async def fetch_json(url, **_):
        return fixture("recruitee/offers.json")
    s.fetch_json = fetch_json
    job = asyncio.run(s.scrape()).jobs[0]
    assert job.location == "Princeton, New Jersey, United States" and job.remote_type == "hybrid"
    assert job.job_url.startswith("https://infoprolearning.recruitee.com/o/senior-product-manager")
    assert (job.pay_rate_min, job.pay_rate_max, job.pay_period) == (140000.0, 180000.0, "year")
    assert job.job_description
