"""Haley Marketing job board RSS type (scrapers.ats.haley)."""
import asyncio
from pathlib import Path

from scrapers.board_scraper import api_url, board_careers_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "haley"


def scraper():
    cls = build_scraper_class({"slug": "hco", "company_name": "H Co", "ats": "haley", "board": "jobs.akraya.com", "careers_url": None})
    return cls()


def test_board_validation_and_urls():
    assert api_url("haley", "jobs.akraya.com") == "https://jobs.akraya.com/rss/rss.smpl?ff=1&view=1"
    assert board_careers_url("haley", "jobs.akraya.com") == "https://jobs.akraya.com/"
    assert api_url("haley", "https://jobs.akraya.com") is None
    assert api_url("haley", "jobs akraya") is None


def test_scrape_and_parse():
    s = scraper()

    async def request(method, url, read, **_):
        assert method == "GET" and url.endswith("/rss/rss.smpl?ff=1&view=1")
        return (FIX / "rss.xml").read_text()
    s._request = request
    result = asyncio.run(s.scrape())
    assert result.success and result.complete and len(result.jobs) == 2
    job = result.jobs[0]
    assert job.title == "Senior Supplier Enablement Specialist" and job.extra["ref_no"] == "26-03185"
    assert job.location == "Neenah, WI" and job.external_job_id == "14367708"
    assert job.job_url.startswith("https://jobs.akraya.com/jb/Senior-Supplier-Enablement-Specialist")
    assert (job.pay_rate_min, job.pay_rate_max, job.pay_period) == (40.0, 45.0, "hour")
    assert job.employment_type_raw == "W2"  # "Contract Type: W2" in the posting
    assert job.posted_date.year == 2026
    assert result.jobs[1].location == "Bangalore, KA"


def test_not_xml_is_unexpected():
    import pytest
    from scrapers.base import UnexpectedResponseError
    with pytest.raises(UnexpectedResponseError):
        scraper().feed_items("<html>banned</html")
