"""Volcanic site type (scrapers.ats.volcanic)."""
import asyncio
from pathlib import Path

from scrapers.ats import volcanic
from scrapers.board_scraper import api_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "volcanic"


def scraper():
    s = build_scraper_class({"slug": "voco", "company_name": "VO Co", "ats": "volcanic",
                             "board": "vallum.example.com", "careers_url": None})()
    s.DETAIL_DELAY_SECONDS = 0
    return s


def test_board_validation_and_urls():
    assert api_url("volcanic", "vallumassociates.com") == "https://vallumassociates.com/jobs"
    assert api_url("volcanic", "vallumassociates.com/jobs?page=2") is None


def test_first_page_then_sitemap_postings(monkeypatch):
    async def robots_allows(url):
        return True
    monkeypatch.setattr(volcanic, "robots_allows", robots_allows)
    s = scraper()
    pages = {"https://vallum.example.com/jobs": "jobs.html", "https://vallum.example.com/job/sitemap.xml": "sitemap.xml",
             "https://vallum.example.com/job/solar-engineer-6062510": "posting.html"}
    fetched = []

    async def page(url):
        fetched.append(url)
        return (FIX / pages[url]).read_text()
    s._page = page
    result = asyncio.run(s.scrape())
    assert result.success and result.complete and len(result.jobs) == 2
    jobs = {j.external_job_id: j for j in result.jobs}
    card = jobs["6044024"]
    assert card.title == "Client Engineering Associate" and card.location == "Charlotte"
    assert card.job_url == "https://vallum.example.com/job/client-engineering-associate-6044024"
    assert card.posted_date is not None and card.extra["salary_text"].startswith("US$65000")
    solar = jobs["6062510"]
    assert solar.title == "Solar Engineer" and solar.location == "Greenwich, Connecticut, United States"
    assert solar.pay_rate_min is None  # 0 - 0 is no salary
    assert fetched.count("https://vallum.example.com/job/client-engineering-associate-6044024") == 0


def test_bot_check_is_a_failure_not_an_empty_board(monkeypatch):
    async def robots_allows(url):
        return True
    monkeypatch.setattr(volcanic, "robots_allows", robots_allows)
    s = scraper()

    async def page(url):
        raise volcanic.BotCheck("vallum.example.com answered 202 (waf action challenge)")
    s._page = page
    result = asyncio.run(s.scrape())
    assert not result.success and "bot check" in result.error_message
