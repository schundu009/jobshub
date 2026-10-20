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

from scrapers.ats.sprockets import sprockets_page


def test_sprockets_board_page():
    assert api_url("sprockets", "pyramidinc") == "https://jobs.sprockets.ai/en-US/pyramidinc/jobs"
    assert api_url("sprockets", "fr-FR/acme") == "https://jobs.sprockets.ai/fr-FR/acme/jobs"
    assert api_url("sprockets", "a b") is None
    assert sprockets_page("<html>no data</html>") == {}
    s = scraper("sprockets", "pyramidinc")

    async def fetch_html(url, params=None):
        assert params == {"page": "1", "itemsPer": "100"}
        return fixture("sprockets/jobs.html")
    s.fetch_html = fetch_html
    result = asyncio.run(s.scrape())
    assert result.complete and len(result.jobs) == 2
    job = result.jobs[0]
    assert job.title == "Curam batch Developer" and job.location == "Raleigh, NC"
    assert job.job_url == "https://jobs.sprockets.ai/en-US/pyramidinc/jobs/0028042e-6f35-4a49-bbcd-468cbb62836e"
    assert (job.pay_rate_min, job.pay_rate_max, job.pay_period) == (80.0, 90.0, "hour")
