"""Sitecore Search job board type (scrapers.ats.sitecore)."""
import asyncio
import json
from pathlib import Path

from scrapers.board_scraper import api_url, board_careers_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "sitecore"
BOARD = "www.horizontaltalent.com/43310396/1188195/01-969afd1f-161be3de6acc0afbc279800d78d6f2e73929d65f"


def test_board_validation_and_urls():
    assert api_url("sitecore", BOARD) == "https://discover.sitecorecloud.io/discover/v2/43310396#www.horizontaltalent.com/1188195"
    assert board_careers_url("sitecore", BOARD) == "https://www.horizontaltalent.com/job-board"
    assert api_url("sitecore", "www.horizontaltalent.com/43310396") is None


def test_scrape_and_parse():
    s = build_scraper_class({"slug": "scco", "company_name": "SC Co", "ats": "sitecore", "board": BOARD, "careers_url": None})()
    sent = []

    async def fetch_json(url, method="GET", json_data=None, headers=None, **_):
        sent.append((url, json_data, headers))
        return json.loads((FIX / "search.json").read_text())
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    url, body, headers = sent[0]
    assert url == "https://discover.sitecorecloud.io/discover/v2/43310396" and headers["Authorization"].startswith("01-")
    assert body["widget"]["items"][0]["sources"] == ["1188195"]
    assert result.success and result.complete and len(result.jobs) == 3
    a, b, c = result.jobs
    assert a.location == "California" and a.job_url == "https://www.horizontaltalent.com/job-board/76667"
    assert b.location == "Alameda, CA" and c.location == "Maplewood, Minnesota"
    assert a.employment_type_raw == "Contract" and a.employment_type == "contract"
