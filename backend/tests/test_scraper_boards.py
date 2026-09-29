"""Offline tests for ATS mixins, disabled scrapers and empty/unexpected-result handling."""
import asyncio
from datetime import datetime, timedelta

import pytest

from scrapers.base import (
    HTTPScraper,
    ScraperConfig,
    ScraperErrorType,
    ScraperType,
    UnexpectedResponseError,
)
from scrapers.custom.remaining_scrapers import (
    AshbyMixin,
    GreenhouseMixin,
    WorkdayMixin,
    _parse_workday_posted_on,
)
from scrapers.registry import ScraperRegistry


def _cfg(slug, **kw):
    return ScraperConfig(company_slug=slug, company_name=slug.title(),
                         careers_url="https://example.com", scraper_type=ScraperType.HTTP, **kw)


class FakeWorkday(WorkdayMixin, HTTPScraper):
    config = _cfg("fakeworkday")
    API_URL = "https://acme.wd5.myworkdayjobs.com/wday/cxs/acme/Acme_Careers/jobs"


class FakeGreenhouse(GreenhouseMixin, HTTPScraper):
    config = _cfg("fakegreenhouse")
    API_URL = "https://boards-api.greenhouse.io/v1/boards/acme/jobs"


class FakeAshby(AshbyMixin, HTTPScraper):
    config = _cfg("fakeashby")
    API_URL = "https://api.ashbyhq.com/posting-api/job-board/acme"


def _with_response(scraper, payload, calls=None):
    async def fetch_json(url, method="GET", params=None, json_data=None, **_):
        if calls is not None:
            calls.append((url, method, json_data))
        return payload(json_data) if callable(payload) else payload
    scraper.fetch_json = fetch_json
    return scraper


def test_workday_posted_on_relative_strings():
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    assert _parse_workday_posted_on("Posted Today") == today
    assert _parse_workday_posted_on("Posted Yesterday") == today - timedelta(days=1)
    assert _parse_workday_posted_on("Posted 30+ Days Ago") == today - timedelta(days=30)
    assert _parse_workday_posted_on("2026-01-05") == datetime(2026, 1, 5)
    assert _parse_workday_posted_on("") is None


def test_workday_job_url_drops_tenant_and_page_size_is_20():
    posting = {"title": "Engineer", "externalPath": "/job/NYC/Engineer_R123",
               "locationsText": "NYC", "postedOn": "Posted 3 Days Ago", "bulletFields": ["R123"]}
    calls = []
    s = _with_response(FakeWorkday(), lambda body: {"total": 1, "jobPostings": [posting] if body["offset"] == 0 else []}, calls)
    result = asyncio.run(s.scrape())
    assert result.jobs_found == 1
    job = result.jobs[0]
    assert job.job_url == "https://acme.wd5.myworkdayjobs.com/Acme_Careers/job/NYC/Engineer_R123"
    assert job.external_job_id == "R123"
    assert calls[0][1] == "POST" and calls[0][2]["limit"] <= 20


def test_greenhouse_honors_url_override():
    calls = []
    s = _with_response(FakeGreenhouse(), {"jobs": [{"id": 1, "title": "SWE", "absolute_url": "u", "location": {"name": "X"}}]}, calls)
    s.url_override = "https://boards-api.greenhouse.io/v1/boards/acme2/jobs"
    result = asyncio.run(s.scrape())
    assert calls[0][0] == s.url_override
    assert result.jobs_found == 1


def test_unexpected_shape_raises():
    s = _with_response(FakeGreenhouse(), {"error": "moved"})
    s.url_override = FakeGreenhouse.API_URL
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(s.scrape())


def test_all_postings_unparseable_raises():
    s = FakeAshby()
    s.parse_job = lambda raw: None
    _with_response(s, {"jobs": [{"id": "a"}, {"id": "b"}]})
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(s.scrape())


def test_run_reports_unexpected_response_as_failure():
    s = _with_response(FakeAshby(), {"html": "<p>gone</p>"})
    s.config = _cfg("fakeashby", max_retries=1)
    result = asyncio.run(s.run())
    assert not result.success
    assert result.error_type == ScraperErrorType.UNEXPECTED_RESPONSE


def test_run_flags_empty_result_when_board_had_jobs(monkeypatch):
    s = _with_response(FakeAshby(), {"jobs": []})
    monkeypatch.setattr(s, "previously_had_jobs", lambda: True)
    result = asyncio.run(s.run())
    assert not result.success
    assert result.error_type == ScraperErrorType.EMPTY_RESULT


def test_run_allows_empty_for_new_or_allow_empty_boards(monkeypatch):
    s = _with_response(FakeAshby(), {"jobs": []})
    monkeypatch.setattr(s, "previously_had_jobs", lambda: False)
    assert asyncio.run(s.run()).success

    s2 = _with_response(FakeAshby(), {"jobs": []})
    s2.config = _cfg("fakeashby", allow_empty=True)
    monkeypatch.setattr(s2, "previously_had_jobs", lambda: True)
    assert asyncio.run(s2.run()).success


def test_ashby_skips_unlisted_and_keeps_description():
    s = _with_response(FakeAshby(), {"jobs": [
        {"id": "1", "title": "A", "jobUrl": "u1", "location": "SF", "descriptionHtml": "<p>d</p>", "isListed": True},
        {"id": "2", "title": "B", "jobUrl": "u2", "isListed": False},
    ]})
    result = asyncio.run(s.scrape())
    assert [j.external_job_id for j in result.jobs] == ["1"]
    assert result.jobs[0].job_description == "<p>d</p>"


def test_disabled_scrapers_are_not_registered():
    disabled = ScraperRegistry.get_disabled()
    for slug in ["pulumi", "aurora", "rippling", "ripplematch"]:
        assert slug in disabled and disabled[slug]["reason"].startswith("board dead as of")
        assert ScraperRegistry.get(slug) is None
    assert not set(disabled) & set(ScraperRegistry.list_slugs())


@pytest.mark.parametrize("slug,fragment", [
    ("1password", "api.ashbyhq.com/posting-api/job-board/1password"),
    ("cohere", "api.ashbyhq.com/posting-api/job-board/cohere"),
    ("snowflake", "api.ashbyhq.com/posting-api/job-board/snowflake"),
    ("shieldai", "api.lever.co/v0/postings/shieldai"),
    ("sentinelone", "boards/sentinellabs/"),
    ("hubspot", "boards/hubspotjobs/"),
    ("zendesk", "zendesk.wd1.myworkdayjobs.com/wday/cxs/zendesk/zendesk/jobs"),
])
def test_moved_boards_point_at_new_ats(slug, fragment):
    assert fragment in ScraperRegistry.get(slug).API_URL
