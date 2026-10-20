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


def test_rippling_board():
    assert api_url("rippling", "hammerspace") == "https://ats.rippling.com/api/v2/board/hammerspace/jobs"
    assert board_careers_url("rippling", "hammerspace") == "https://ats.rippling.com/hammerspace/jobs"
    assert api_url("rippling", "a/b") is None
    s = scraper("rippling", "redesigncareers")
    job = s.parse_job({"id": "1a", "name": "Infrastructure Engineer", "url": "https://ats.rippling.com/redesigncareers/jobs/1a",
                       "locations": [{"name": "Hybrid (Boston, Massachusetts, US)", "workplaceType": "HYBRID"}]})
    assert job.location == "Hybrid (Boston, Massachusetts, US)" and job.remote_type == "hybrid"
