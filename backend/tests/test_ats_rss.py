"""RSS job feed type (scrapers.ats.rss)."""
import asyncio
from pathlib import Path

from scrapers.board_scraper import api_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "rss"


def test_board_validation_and_urls():
    assert api_url("rss", "careers.cblsolutions.com/?feed=job_feed") == "https://careers.cblsolutions.com/?feed=job_feed"
    assert api_url("rss", "https://example.com/feed/") is None
    assert api_url("rss", "not a host") is None


def test_scrape_and_parse():
    s = build_scraper_class({"slug": "rsco", "company_name": "RS Co", "ats": "rss",
                             "board": "www.example-wpjm.com/?feed=job_feed", "careers_url": None})()

    async def request(method, url, read, **_):
        return (FIX / "job_feed.xml").read_text()
    s._request = request
    result = asyncio.run(s.scrape())
    assert result.success and len(result.jobs) == 2
    a, b = result.jobs
    assert a.title == "Payroll Specialist" and a.location == "New York, New York"
    assert a.employment_type_raw == "Permanent" and (a.pay_rate_min, a.pay_rate_max, a.pay_period) == (65000.0, 80000.0, "year")
    assert a.job_url == "https://www.example-wpjm.com/job/2005778895358-payroll-specialist-new-york/"
    assert a.posted_date.year == 2026 and a.extra["client"] == "Example Recruitment"
    assert b.external_job_id == "1769" and b.location == "United States" and b.posted_date.year == 2024
