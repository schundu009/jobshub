"""HTML job listing type (scrapers.ats.jobpages)."""
import asyncio
from pathlib import Path

from scrapers.ats import jobpages
from scrapers.board_scraper import api_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "jobpages"


def test_board_validation_and_urls():
    assert api_url("jobpages", "www.redfishtech.com/job-board/") == "https://www.redfishtech.com/job-board/"
    assert api_url("jobpages", "example.com/openings/|/vacancy/") == "https://example.com/openings/"
    assert api_url("jobpages", "https://example.com/jobs/") is None


def test_listing_cards_pagination_and_posting_page(monkeypatch):
    allowed = []

    async def robots_allows(url):
        allowed.append(url)
        return True
    monkeypatch.setattr(jobpages, "robots_allows", robots_allows)
    s = build_scraper_class({"slug": "jpco", "company_name": "JP Co", "ats": "jobpages",
                             "board": "www.example-firm.com/job-board/", "careers_url": None})()
    pages = {
        "https://www.example-firm.com/job-board/": "listing.html",
        "https://www.example-firm.com/job-board/page/2/": "listing_page2.html",
        "https://www.example-firm.com/jobs/chief-financial-officer-4835/": "posting.html",
    }
    fetched = []

    async def fetch_html(url, params=None):
        fetched.append(url)
        return (FIX / pages[url]).read_text()
    s.fetch_html = fetch_html
    result = asyncio.run(s.scrape())
    assert result.success and result.complete
    jobs = {j.title: j for j in result.jobs}
    assert set(jobs) == {"Data Engineer 1", "Desktop Support Specialist", "Chief Financial Officer", "Infrastructure Engineer"}
    assert jobs["Data Engineer 1"].location == "Remote"
    assert (jobs["Data Engineer 1"].pay_rate_min, jobs["Data Engineer 1"].pay_period) == (70.0, "hour")
    assert jobs["Desktop Support Specialist"].location == "San Diego, CA"
    assert jobs["Desktop Support Specialist"].job_url == "https://www.example-firm.com/jobs/desktop-support-specialist/"
    assert jobs["Infrastructure Engineer"].location == "Portland, OR"
    assert jobs["Infrastructure Engineer"].external_job_id == "15814"
    cfo = jobs["Chief Financial Officer"]  # card has no location: read from the posting's JobPosting
    assert cfo.location == "London, United Kingdom" and cfo.employment_type_raw == "FULL_TIME"
    assert (cfo.pay_rate_min, cfo.pay_rate_max, cfo.pay_period) == (185000.0, 250000.0, "year")
    assert "https://www.example-firm.com/jobs/feed/" not in fetched and len(fetched) == 3
    assert all(u in allowed for u in fetched)


def test_robots_disallow_stops(monkeypatch):
    async def robots_allows(url):
        return False
    monkeypatch.setattr(jobpages, "robots_allows", robots_allows)
    s = build_scraper_class({"slug": "jpco2", "company_name": "JP Co", "ats": "jobpages",
                             "board": "www.example-firm.com/job-board/", "careers_url": None})()
    result = asyncio.run(s.scrape())
    assert not result.success and "robots.txt" in result.error_message
