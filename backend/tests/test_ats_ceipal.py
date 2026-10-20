"""Ceipal portals as job_boards rows: board check, job links, parsing, and the browser queue."""
import asyncio

from scrapers.ats import ceipal
from scrapers.base import ScraperType
from scrapers.board_scraper import api_url, board_metadata, build_scraper_class

BOARD = "acmestaffing.com/careers/search-job/"
ROW = {"slug": "acmestaffing", "company_name": "Acme Staffing", "ats": "ceipal", "board": BOARD, "careers_url": None}

# One row of careerapi.ceipal.com/<key>/CareerPortalJobPostings/ (synthetic values, the API's field names).
RAW = {
    "id": "z5G7h3l6a1kMvyS65NP3cwdhlRRFNony9Uu14AFKcNA=",
    "remote_opportunities": 1,
    "public_job_desc": "Job Title: SAP Load Test Analyst\r\n\r\nDuration (Contract): 8 Months....",
    "job_code": "JPC - 94913",
    "public_job_title": "SAP Load Test Analyst",
    "country": "United States",
    "state": "Pennsylvania",
    "tax_terms": "C2C, W-2 Hourly",
    "updated": "Yesterday",
    "multpile_job_location": "(Middletown, PA, 17057)",
}


def test_board_is_the_careers_page_without_scheme():
    assert ceipal.valid_board(BOARD)
    assert ceipal.valid_board("www.example.com/usa")
    assert not ceipal.valid_board("https://acmestaffing.com/careers/")
    assert not ceipal.valid_board("not a host")
    assert not ceipal.valid_board("")
    assert api_url("ceipal", BOARD) == f"https://{BOARD}"
    assert api_url("ceipal", "https://x.com/") is None


def test_job_url_opens_the_job_on_the_firms_page():
    assert ceipal.job_url(BOARD, "abc=") == "https://acmestaffing.com/careers/search-job/?job_id=abc%3D"
    assert ceipal.job_url("x.com/jobs?lang=en&job_id=old", "new") == "https://x.com/jobs?lang=en&job_id=new"


def test_location_reads_the_multi_location_text():
    assert ceipal.location_of(RAW) == "Middletown, PA"
    two = {"multpile_job_location": "(Austin, TX, 78701), (Dallas, TX)"}
    assert ceipal.location_of(two) == "Austin, TX; Dallas, TX"
    assert ceipal.location_of({"state": "Texas", "country": "United States"}) == "Texas, United States"


def test_row_builds_a_browser_scraper_that_parses_jobs():
    cls = build_scraper_class(ROW)
    assert cls is not None
    assert cls.config.scraper_type == ScraperType.PLAYWRIGHT
    assert board_metadata(ROW)["scraper_type"] == ScraperType.PLAYWRIGHT.value
    job = cls().parse_job(RAW)
    assert job.title == "SAP Load Test Analyst"
    assert job.location == "Middletown, PA (Remote)"
    assert job.remote_type == "remote"
    assert job.external_job_id == "JPC - 94913"
    assert job.job_url.startswith("https://acmestaffing.com/careers/search-job/?job_id=")
    assert job.extra == {"tax_terms": "C2C, W-2 Hourly"}
    assert cls().parse_job({"id": "", "public_job_title": "x"}) is None


def test_no_display_fails_clearly(monkeypatch):
    monkeypatch.setattr(ceipal, "has_display", lambda: False)
    cls = build_scraper_class(ROW)
    result = asyncio.run(cls().scrape())
    assert not result.success
    assert "DISPLAY" in result.error_message


def test_scrape_merges_widgets_and_drops_repeats(monkeypatch):
    monkeypatch.setattr(ceipal, "has_display", lambda: True)
    other = dict(RAW, id="second", job_code="JPC - 2", public_job_title="Data Engineer")

    async def fake_pages(self, url):
        assert url == f"https://{BOARD}"
        return {("keyA", 1): [RAW], ("keyB", 1): [RAW, other]}, 2

    monkeypatch.setattr(ceipal.CeipalMixin, "_read_pages", fake_pages)
    result = asyncio.run(build_scraper_class(ROW)().scrape())
    assert result.success and result.complete
    assert [j.title for j in result.jobs] == ["SAP Load Test Analyst", "Data Engineer"]
