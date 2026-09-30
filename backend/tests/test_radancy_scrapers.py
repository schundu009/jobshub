"""Offline tests for the Radancy TalentBrew scrapers and the Cognizant XML feed scraper."""
import asyncio
from datetime import datetime

import pytest

from scrapers.base import UnexpectedResponseError
from scrapers.enterprise.cognizant_feed import CognizantFeedScraper
from scrapers.enterprise.radancy_scrapers import (
    ChipotleRadancyScraper,
    OptumRadancyScraper,
    WalgreensRadancyScraper,
)
from scrapers.registry import ScraperRegistry


def _li(job_id, href, title, location, extra="", cls=""):
    cls_attr = f' class="{cls}"' if cls else ""
    return (
        f'<li><a href="{href}" data-job-id="{job_id}"{cls_attr}><h2>{title}</h2>'
        f'<span class="job-location">{location}</span>{extra}</a></li>'
    )


def _page(items, total_pages=1, current=1):
    return (
        f'<section id="search-results" data-total-pages="{total_pages}" data-current-page="{current}">'
        f'<section id="search-results-list"><ul>{"".join(items)}</ul></section></section>'
    )


def _with_pages(scraper, pages, calls):
    """pages: {page_number: results_html}; missing pages return an empty list."""
    async def fetch_json(url, method="GET", params=None, headers=None, **_):
        calls.append((url, params, headers))
        page = int(params["CurrentPage"])
        return {"results": pages.get(page, _page([])), "hasJobs": page in pages}
    scraper.url_override = scraper._results_url()  # skip the DB lookup
    scraper.fetch_json = fetch_json
    return scraper


def test_radancy_paginates_dedupes_and_builds_public_urls():
    s = WalgreensRadancyScraper()
    s.RECORDS_PER_PAGE = 2
    s.TIME_BUDGET_SECONDS = 60
    pages = {
        1: _page([_li("11", "/en/job/new-york/shift-lead/1242/11", "Shift Lead", "New York, New York"),
                  _li("12", "/en/job/austin/pharmacist/1242/12", "Pharmacist", "Austin, Texas")], total_pages=2),
        2: _page([_li("12", "/en/job/austin/pharmacist/1242/12", "Pharmacist", "Austin, Texas"),
                  _li("13", "/en/job/remote/analyst/1242/13", "Analyst", "Remote")], total_pages=2, current=2),
    }
    calls = []
    result = asyncio.run(_with_pages(s, pages, calls).scrape())

    assert result.success and result.jobs_found == 3
    assert [j.external_job_id for j in result.jobs] == ["11", "12", "13"]
    assert result.jobs[0].job_url == "https://jobs.walgreens.com/en/job/new-york/shift-lead/1242/11"
    assert result.jobs[1].title == "Pharmacist" and result.jobs[1].location == "Austin, Texas"
    assert len(calls) == 2  # stopped at data-total-pages
    url, params, headers = calls[0]
    assert url == "https://jobs.walgreens.com/en/search-jobs/results"
    assert params["SearchType"] == "5" and "SearchFiltersModuleName" not in params
    assert headers == {"X-Requested-With": "XMLHttpRequest"}


def test_radancy_optum_keeps_only_optum_brand_and_parses_extras():
    s = OptumRadancyScraper()
    extra = ('<span class="job-id job-info">2390728</span>'
             '<span class="job-info job-worksetting">Remote</span>')
    pages = {1: _page([
        _li("1", "/job/dallas/nurse/34088/1", "Nurse", "Dallas, Texas", extra, cls="brand-facet brand-facet__optum"),
        _li("2", "/job/dallas/agent/34088/2", "Agent", "Dallas, Texas", cls="brand-facet brand-facet__uhc"),
    ])}
    result = asyncio.run(_with_pages(s, pages, []).scrape())
    assert [j.title for j in result.jobs] == ["Nurse"]
    job = result.jobs[0]
    assert job.job_url == "https://careers.unitedhealthgroup.com/job/dallas/nurse/34088/1"
    assert job.remote_type == "remote"


def test_radancy_respects_max_jobs():
    s = ChipotleRadancyScraper()
    s.MAX_JOBS = 3
    items = [_li(str(i), f"/job/x/crew/282/{i}", "Crew", "Denver, CO") for i in range(5)]
    calls = []
    result = asyncio.run(_with_pages(s, {1: _page(items, total_pages=9), 2: _page(items)}, calls).scrape())
    assert result.jobs_found == 3
    assert len(calls) == 1


def test_radancy_changed_markup_raises():
    s = ChipotleRadancyScraper()
    pages = {1: '<section id="search-results"><div class="card">Crew</div></section>'}
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(_with_pages(s, pages, []).scrape())

    s2 = ChipotleRadancyScraper()
    s2.url_override = s2._results_url()

    async def not_talentbrew(*a, **k):
        return {"error": "gone"}
    s2.fetch_json = not_talentbrew
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(s2.scrape())


FEED = """<?xml version="1.0" encoding="utf-8"?>
<source>
  <publisher>Cognizant</publisher>
  <job>
    <title><![CDATA[Sr AI/ML Engineer]]></title>
    <date><![CDATA[Tue, 29 Sep 2026 18:25:18 GMT]]></date>
    <requisitionid><![CDATA[00070835994]]></requisitionid>
    <url><![CDATA[https://careers.cognizant.com/global-en/jobs/00070835994/sr-aiml-engineer/]]></url>
    <city><![CDATA[Chicago]]></city>
    <state><![CDATA[Illinois]]></state>
    <country><![CDATA[United States]]></country>
    <description><![CDATA[<p>Build models</p>]]></description>
    <jobtype><![CDATA[Full-time]]></jobtype>
    <category><![CDATA[Digital]]></category>
    <remotetype><![CDATA[Hybrid remote]]></remotetype>
  </job>
  <job>
    <title><![CDATA[Analyst]]></title>
    <requisitionid><![CDATA[00070000001]]></requisitionid>
    <url><![CDATA[https://careers.cognizant.com/global-en/jobs/00070000001/analyst/]]></url>
    <city><![CDATA[Pune]]></city>
    <country><![CDATA[India]]></country>
  </job>
</source>"""


def _cognizant(payload):
    s = CognizantFeedScraper()
    s.url_override = CognizantFeedScraper.API_URL

    async def fetch_html(url, params=None):
        return payload
    s.fetch_html = fetch_html
    return s


def test_cognizant_feed_parses_jobs():
    result = asyncio.run(_cognizant(FEED).scrape())
    assert result.success and result.jobs_found == 2
    job = result.jobs[0]
    assert job.title == "Sr AI/ML Engineer"
    assert job.external_job_id == "00070835994"
    assert job.job_url.endswith("/jobs/00070835994/sr-aiml-engineer/")
    assert job.location == "Chicago, Illinois, United States"
    assert job.department == "Digital"
    assert job.remote_type == "hybrid"
    assert job.employment_type == "full-time"
    assert job.posted_date == datetime(2026, 9, 29, 18, 25, 18)
    assert job.job_description == "<p>Build models</p>"
    assert result.jobs[1].location == "Pune, India" and result.jobs[1].posted_date is None


def test_cognizant_challenge_page_raises():
    challenge = "<!DOCTYPE html><html><head><title>Just a moment...</title></head></html>"
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(_cognizant(challenge).scrape())


def test_registry_uses_new_scrapers():
    assert ScraperRegistry.get("optum") is OptumRadancyScraper
    assert ScraperRegistry.get("chipotle") is ChipotleRadancyScraper
    assert ScraperRegistry.get("walgreens") is WalgreensRadancyScraper
    assert ScraperRegistry.get("cognizant") is CognizantFeedScraper
