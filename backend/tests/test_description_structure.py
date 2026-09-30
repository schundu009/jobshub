"""Scraped descriptions keep their structure (headings, paragraphs, bullets)."""
import asyncio

from scrapers.base import BaseScraper
from scrapers.enterprise.salesforce import SalesforceScraper

HTML = (
    "<p><b>About the role</b></p><p>You will build things &amp; ship.</p>"
    "<h3>Requirements</h3><ul><li>5+ years Go</li><li>K8s</li></ul><p>Line<br>two</p>"
    "<script>track()</script>"
)


def test_clean_html_keeps_headings_paragraphs_and_bullets():
    assert BaseScraper.clean_html(None, HTML) == (
        "About the role\n\nYou will build things & ship.\n\nRequirements\n\n- 5+ years Go\n- K8s\n\nLine\ntwo"
    )


def test_clean_html_empty_and_plain():
    assert BaseScraper.clean_html(None, None) is None
    assert BaseScraper.clean_html(None, "  ") is None
    assert BaseScraper.clean_html(None, "plain text only") == "plain text only"


def test_salesforce_keeps_description_html(monkeypatch):
    scraper = SalesforceScraper()

    async def fake_fetch_json(url, **kwargs):
        return {"jobPostingInfo": {
            "title": "Platform Engineer", "jobReqId": "JR1", "location": "Seattle",
            "jobDescription": "<p><b>Responsibilities</b></p><ul><li>Own the pipeline</li></ul>"
                              "<p>The typical base salary range for this position is $140,000 - $210,000 annually.</p>",
            "startDate": "2026-09-01",
        }}

    monkeypatch.setattr(scraper, "fetch_json", fake_fetch_json)
    job = asyncio.run(scraper._fetch_job_details("/job/Seattle/Platform-Engineer_JR1", {}))
    assert job.job_description.startswith("<p><b>Responsibilities</b></p><ul><li>Own the pipeline</li></ul>")
    assert (job.salary_min, job.salary_max) == (140000, 210000)
