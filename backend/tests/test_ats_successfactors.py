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

from bs4 import BeautifulSoup

from scrapers.enterprise.successfactors_scrapers import SuccessFactorsMixin


def test_tile_layout_rows():
    soup = BeautifulSoup(fixture("successfactors/tiles_search.html"), "html.parser")
    rows = SuccessFactorsMixin.parse_search_page(soup, "https://careers.paramount.com")
    assert len(rows) == 2 and SuccessFactorsMixin.sf_total(soup) == 278
    assert rows[0]["title"] and rows[0]["location"] and rows[0]["url"].startswith("https://careers.paramount.com/job/")
    assert rows[0]["id"].isdigit()


def test_unify_site_reads_the_jobs_api():
    s = scraper("successfactors", "careers.hcltech.com")
    posts = []

    async def fetch_html(url, params=None):
        return fixture("successfactors/unify_search.html")

    async def fetch_json(url, method="GET", json_data=None, **_):
        posts.append((url, json_data["pageNumber"], json_data["sortBy"]))
        data = fixture("successfactors/unify_jobs.json")
        data["totalJobs"] = 2
        return data
    s.fetch_html, s.fetch_json = fetch_html, fetch_json
    result = asyncio.run(s.scrape())
    assert posts == [("https://careers.hcltech.com/services/recruiting/v1/jobs", 0, "date")]
    assert result.complete and len(result.jobs) == 2
    job = result.jobs[0]
    assert job.title == "Administrator - Wireless Networking" and job.location == "Beijing, China"
    assert job.job_url == "https://careers.hcltech.com/job/Administrator-Wireless-Networking/157085-en_US/"
    assert job.posted_date.year == 2026


def test_ashby_org_names_with_spaces():
    assert api_url("ashby", "Grindr LLC") == "https://api.ashbyhq.com/posting-api/job-board/Grindr%20LLC"
    assert board_careers_url("ashby", "Grindr LLC") == "https://jobs.ashbyhq.com/Grindr%20LLC"
    assert api_url("ashby", "a/b") is None and api_url("ashby", " lead") is None
