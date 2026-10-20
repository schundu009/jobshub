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


def test_eightfold_board_and_variant_pick():
    assert api_url("eightfold", "paypal.eightfold.ai/paypal.com") == \
        "https://paypal.eightfold.ai/api/pcsx/search?domain=paypal.com"
    assert board_careers_url("eightfold", "paypal.eightfold.ai/paypal.com") == \
        "https://paypal.eightfold.ai/careers?domain=paypal.com"
    assert api_url("eightfold", "paypal.eightfold.ai") is None
    s = scraper("eightfold", "explore.jobs.netflix.net/netflix.com")
    calls = []

    async def fetch_json(url, params=None, **_):
        calls.append(url.rsplit("/api/", 1)[1])
        if "pcsx" in url:
            return {"message": "PCSX is not enabled for this domain"}
        return {"count": 1, "positions": [{"id": 7, "name": "SRE", "location": "Los Gatos", "t_create": 1789488443,
                                           "canonicalPositionUrl": "https://explore.jobs.netflix.net/careers/job/7"}]}
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert s.API_VARIANT == "apply_v2" and calls[0] == "pcsx/search"
    assert result.jobs[0].title == "SRE" and result.jobs[0].job_url.endswith("/careers/job/7")
