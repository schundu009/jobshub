"""Offline tests for the Eightfold mixin (apply/v2 and PCSX variants)."""
import asyncio
from datetime import datetime

import pytest

from scrapers.base import UnexpectedResponseError
from scrapers.enterprise.eightfold_scrapers import (
    EightfoldMixin,
    NetflixEightfoldScraper,
    VodafoneEightfoldScraper,
)
from scrapers.registry import ScraperRegistry


def _with_pages(scraper, page_for_start, calls=None):
    async def fetch_json(url, method="GET", params=None, json_data=None, **_):
        if calls is not None:
            calls.append((url, dict(params or {})))
        return page_for_start(int((params or {}).get("start", 0)))
    scraper.fetch_json = fetch_json
    return scraper


def _apply_v2_position(i):
    return {
        "id": 1000 + i, "name": f"Engineer {i}", "location": "Los Gatos, California",
        "locations": ["Los Gatos, California", "Los Angeles, California"],
        "department": "Engineering", "t_create": 1790000000, "t_update": 1790500000,
        "display_job_id": f"JR{i}", "ats_job_id": f"JR{i}", "work_location_option": "onsite",
        "canonicalPositionUrl": f"https://explore.jobs.netflix.net/careers/job/{1000 + i}",
        "job_description": "",
    }


def _pcsx_position(i):
    return {
        "id": 5000 + i, "displayJobId": str(200 + i), "name": f"Analyst {i}",
        "location": "Remote, United Kingdom", "locations": ["Remote, United Kingdom"],
        "department": "Finance", "postedTs": 1790696475, "creationTs": 1787132494,
        "atsJobId": str(200 + i), "workLocationOption": "onsite",
        "positionUrl": f"/careers/job/{5000 + i}",
    }


def test_apply_v2_paginates_and_parses():
    total = 23
    positions = [_apply_v2_position(i) for i in range(total)]
    calls = []
    s = _with_pages(NetflixEightfoldScraper(),
                    lambda start: {"count": total, "positions": positions[start:start + 10]}, calls)
    result = asyncio.run(s.scrape())

    assert result.success and result.jobs_found == total
    assert sorted(c[1]["start"] for c in calls) == [0, 10, 20]
    assert all(c[0] == "https://explore.jobs.netflix.net/api/apply/v2/jobs" for c in calls)
    assert calls[0][1]["domain"] == "netflix.com"
    job = next(j for j in result.jobs if j.external_job_id == "JR0")
    assert job.title == "Engineer 0"
    assert job.job_url == "https://explore.jobs.netflix.net/careers/job/1000"
    assert job.location == "Los Gatos, California; Los Angeles, California"
    assert job.department == "Engineering"
    assert job.posted_date == datetime.utcfromtimestamp(1790000000)
    assert job.remote_type == "on-site"


def test_pcsx_unwraps_data_and_builds_absolute_urls():
    total = 12
    positions = [_pcsx_position(i) for i in range(total)]
    calls = []
    s = _with_pages(VodafoneEightfoldScraper(),
                    lambda start: {"status": 200, "data": {"count": total, "positions": positions[start:start + 10]}},
                    calls)
    result = asyncio.run(s.scrape())

    assert result.jobs_found == total
    assert calls[0][0] == "https://jobs.vodafone.com/api/pcsx/search"
    assert calls[0][1]["domain"] == "vodafone.com" and calls[0][1]["query"] == ""
    job = next(j for j in result.jobs if j.external_job_id == "200")
    assert job.job_url == "https://jobs.vodafone.com/careers/job/5000"
    assert job.posted_date == datetime.utcfromtimestamp(1790696475)
    assert job.remote_type == "remote"  # location wins over the onsite tag


def test_duplicates_across_pages_are_dropped():
    page = [_apply_v2_position(i) for i in range(10)]
    s = _with_pages(NetflixEightfoldScraper(), lambda start: {"count": 20, "positions": page})
    result = asyncio.run(s.scrape())
    assert result.jobs_found == 10


def test_not_authorized_response_raises_unexpected():
    s = _with_pages(VodafoneEightfoldScraper(), lambda start: {"message": "Not authorized for PCSX"})
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(s.scrape())


def test_max_jobs_caps_pages():
    class Capped(NetflixEightfoldScraper):
        MAX_JOBS = 30
    calls = []
    s = _with_pages(Capped(), lambda start: {"count": 1000, "positions": [_apply_v2_position(start + i) for i in range(10)]}, calls)
    result = asyncio.run(s.scrape())
    assert result.jobs_found == 30 and len(calls) == 3


def test_registered_under_original_slugs():
    for slug, cls in [("netflix", NetflixEightfoldScraper), ("vodafone", VodafoneEightfoldScraper)]:
        assert ScraperRegistry.get(slug) is cls
        assert issubclass(cls, EightfoldMixin)


def test_vodafone_drops_istanbul_only_postings():
    s = VodafoneEightfoldScraper()
    assert s.parse_job({"id": 1, "name": "Network Engineer", "location": "İstanbul, Turkey"}) is None
    kept = s.parse_job({"id": 2, "name": "Network Engineer", "location": "İstanbul, Turkey", "locations": ["London, UK"]})
    assert kept is not None


def test_dotted_capital_i_city_resolves():
    from services.job_location import _segment_countries
    assert _segment_countries("İstanbul, Turkey")[0] == {"TR"}
