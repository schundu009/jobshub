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

def test_desres_openings_page():
    assert api_url("desres", "current-opportunities.html") == \
        "https://www.deshawresearch.com/current-opportunities.html"
    assert api_url("desres", "../etc") is None
    s = scraper("desres", "current-opportunities.html")

    async def fetch_html(url, params=None):
        return fixture("desres/current-opportunities.html")
    s.fetch_html = fetch_html
    job = asyncio.run(s.scrape()).jobs[0]
    assert job.title == "Data Associate" and job.external_job_id == "909"
    assert job.job_url.startswith("https://apply.deshawresearch.com/careers/Register?pipelineId=909")
    assert (job.salary_min, job.salary_max) == (170000, 210000) and job.location == "New York, NY"
