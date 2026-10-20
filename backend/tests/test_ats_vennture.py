"""Vennture gateway type (scrapers.ats.vennture)."""
import asyncio
import json
from pathlib import Path

from scrapers.board_scraper import api_url, board_careers_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "vennture"


def test_board_validation_and_urls():
    assert api_url("vennture", "www.hamilton-barnes.com") == \
        "https://gateway.wearevennture.co.uk/job-search?local=uk&organisation=#www.hamilton-barnes.com"
    assert board_careers_url("vennture", "www.spectrumit.co.uk") == "https://www.spectrumit.co.uk/"
    assert api_url("vennture", "hamilton barnes") is None


def test_scrape_sends_site_origin_and_parses():
    cls = build_scraper_class({"slug": "vco", "company_name": "V Co", "ats": "vennture",
                               "board": "www.hamilton-barnes.com", "careers_url": None})
    s = cls()
    seen = []

    async def fetch_json(url, method="GET", json_data=None, headers=None, **_):
        seen.append((method, url, json_data, headers))
        name = "auth.json" if "/auth" in url else "search.json"
        return json.loads((FIX / name).read_text())
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert seen[0][3]["Origin"] == "https://www.hamilton-barnes.com"
    method, url, body, headers = seen[1]
    assert method == "POST" and headers["Authorization"] == "Bearer header.payload.signature"
    assert body["pageSize"] == 100 and body["sessionId"] == "sid123" and "nextPageToken" not in body
    assert result.success and result.complete and len(result.jobs) == 2
    a, b = result.jobs
    assert a.job_url == "https://www.hamilton-barnes.com/candidates/job/noc-engineer---systems-integrator-8691/"
    assert a.location == "Anchorage, Alaska, United States" and a.employment_type_raw == "Permanent"
    assert (a.pay_rate_min, a.pay_period, a.salary_min) == (60000.0, "year", 60000)
    assert b.location == "Remote" and b.employment_type == "contract"
    assert (b.pay_rate_min, b.pay_rate_max, b.pay_period) == (500.0, 550.0, "day")


def test_no_session_fails_cleanly():
    cls = build_scraper_class({"slug": "vco2", "company_name": "V Co", "ats": "vennture",
                               "board": "www.spectrumit.co.uk", "careers_url": None})
    s = cls()

    async def fetch_json(url, **_):
        return {"features": []}
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert not result.success and "session" in result.error_message
