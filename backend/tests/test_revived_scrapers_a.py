"""Offline tests for revived scrapers: Arm (Radancy), EA (Avature), Rippling ATS, Deel ATS (Deel, Klarna)."""
import asyncio
import json

import pytest

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType, UnexpectedResponseError
from scrapers.enterprise.avature_scrapers import AvatureMixin
from scrapers.enterprise.deel_ats_scrapers import DeelATSMixin, decode_flight
from scrapers.enterprise.radancy_scrapers import RadancyMixin
from scrapers.enterprise.rippling_ats_scrapers import RipplingATSMixin
from scrapers.registry import ScraperRegistry


def _cfg(slug, **kw):
    return ScraperConfig(company_slug=slug, company_name=slug.title(),
                         careers_url="https://example.com", scraper_type=ScraperType.HTTP, **kw)


class FakeRippling(RipplingATSMixin, HTTPScraper):
    config = _cfg("fakerippling")
    BOARD = "acme"


class FakeDeel(DeelATSMixin, HTTPScraper):
    config = _cfg("fakedeel")
    BOARD = "acme"


def _no_db(scraper):
    scraper.resolve_api_url = lambda default=None: default
    return scraper


def _flight_page(*objects) -> str:
    """Wrap JSON objects as a Next.js page whose flight stream is split over two chunks."""
    flight = '0:{"a":1}\n5:[' + ",".join(json.dumps(o, separators=(",", ":")) for o in objects) + "]\n"
    half = len(flight) // 2
    pushes = "".join(
        f"<script>self.__next_f.push([1,{json.dumps(part)}])</script>"
        for part in (flight[:half], flight[half:])
    )
    return f"<html><body>{pushes}</body></html>"


# -- registry -----------------------------------------------------------------

@pytest.mark.parametrize("slug,mixin", [
    ("arm", RadancyMixin),
    ("ea", AvatureMixin),
    ("rippling", RipplingATSMixin),
    ("deel", DeelATSMixin),
    ("klarna", DeelATSMixin),
])
def test_revived_scrapers_are_enabled_on_new_ats(slug, mixin):
    cls = ScraperRegistry.get(slug)
    assert cls is not None, f"{slug} not registered"
    assert issubclass(cls, mixin) and issubclass(cls, HTTPScraper)
    assert cls.config.enabled and not cls.config.disabled_reason
    assert slug not in ScraperRegistry.get_disabled()


def test_revived_scrapers_point_at_their_boards():
    assert ScraperRegistry.get("arm").SITE_URL == "https://careers.arm.com"
    assert ScraperRegistry.get("ea").PORTAL_URL == "https://jobs.ea.com/en_US/careers"
    assert ScraperRegistry.get("rippling")().board_api_url() == "https://ats.rippling.com/api/v2/board/rippling/jobs"
    assert ScraperRegistry.get("deel")().board_url() == "https://jobs.deel.com/deel"
    assert ScraperRegistry.get("klarna")().board_url() == "https://jobs.deel.com/klarna"


# -- Arm (Radancy with a custom card template) ---------------------------------

ARM_RESULTS = """
<section id="search-results" data-total-pages="1"><ul id="search-results-list">
<li class="job-card">
  <a class="job-card__title" data-job-id="101" href="/job/cambridge/staff-engineer/33099/101">Staff&nbsp;Engineer</a>
  <span class="job-card__intro">Build things.</span>
  <span class="location">Cambridge, United Kingdom</span>
  <span class="category">Software Engineering</span>
  <button class="js-save-job-btn" data-job-id="101">Save</button>
</li>
<li class="job-card">
  <a class="job-card__title" data-job-id="102" href="/job/austin/verification-engineer/33099/102">Verification Engineer</a>
  <span class="location">Austin, Texas</span>
</li>
</ul></section>
"""


def test_arm_parses_title_location_category_from_card():
    scraper = ScraperRegistry.get("arm")()

    async def fetch_json(url, params=None, headers=None, **_):
        return {"results": ARM_RESULTS, "hasJobs": True}

    _no_db(scraper).fetch_json = fetch_json
    result = asyncio.run(scraper.scrape())
    assert result.jobs_found == 2
    first = result.jobs[0]
    assert first.title == "Staff Engineer"
    assert first.location == "Cambridge, United Kingdom"
    assert first.department == "Software Engineering"
    assert first.external_job_id == "101"
    assert first.job_url == "https://careers.arm.com/job/cambridge/staff-engineer/33099/101"
    assert result.jobs[1].department is None


# -- EA (Avature, department in .list-item-department) -------------------------

EA_PAGE = """
<article class="article article--result"><div class="article__header__text">
  <h3><a class="link" href="https://jobs.ea.com/en_US/careers/JobDetail/Game-Designer-II/215680">Game Designer II</a></h3>
  <div class="article__header__text__subtitle">
    <span class="list-item-location">Hyderabad, India</span><span class="separator">&bull;</span>
    <span class="list-item-id">Role ID 215680</span><span class="separator">&bull;</span>
    <span class="list-item-department">EA Mobile</span>
  </div></div></article>
"""


def test_ea_single_page_reads_location_and_department():
    scraper = ScraperRegistry.get("ea")()

    async def fetch_html(url, params=None):
        return EA_PAGE

    scraper.fetch_html = fetch_html
    result = asyncio.run(scraper.scrape())
    assert result.jobs_found == 1
    job = result.jobs[0]
    assert job.title == "Game Designer II"
    assert job.external_job_id == "215680"
    assert job.location == "Hyderabad, India"
    assert job.department == "EA Mobile"
    assert job.job_url.endswith("/JobDetail/Game-Designer-II/215680")


# -- Rippling ATS ---------------------------------------------------------------

def _rip_item(job_id, name, city, workplace="ON_SITE", dept="Engineering"):
    return {
        "id": job_id, "name": name, "url": f"https://ats.rippling.com/acme/jobs/{job_id}",
        "department": {"name": dept},
        "locations": [{"name": city, "city": city, "workplaceType": workplace}],
    }


def test_rippling_merges_location_rows_and_pages():
    pages = {
        "0": {"items": [_rip_item("a", "SWE", "New York, NY"), _rip_item("a", "SWE", "San Francisco, CA"),
                        _rip_item("b", "PM", "Remote (US)", workplace="REMOTE", dept="Product")],
              "page": 0, "totalPages": 2, "totalItems": 4},
        "1": {"items": [_rip_item("c", "Designer", "London", workplace="HYBRID")],
              "page": 1, "totalPages": 2, "totalItems": 4},
    }
    calls = []

    async def fetch_json(url, params=None, **_):
        calls.append((url, params))
        return pages[params["page"]]

    scraper = _no_db(FakeRippling())
    scraper.fetch_json = fetch_json
    result = asyncio.run(scraper.scrape())
    assert [c[1]["page"] for c in calls] == ["0", "1"]
    assert calls[0][0] == "https://ats.rippling.com/api/v2/board/acme/jobs"
    assert result.jobs_found == 3
    by_id = {j.external_job_id: j for j in result.jobs}
    assert by_id["a"].location == "New York, NY; San Francisco, CA"
    assert by_id["a"].job_url == "https://ats.rippling.com/acme/jobs/a"
    assert by_id["a"].remote_type == "on-site"
    assert by_id["b"].remote_type == "remote" and by_id["b"].department == "Product"
    assert by_id["c"].remote_type == "hybrid"


def test_rippling_rejects_unexpected_payload():
    async def fetch_json(url, params=None, **_):
        return {"error": "not found"}

    scraper = _no_db(FakeRippling())
    scraper.fetch_json = fetch_json
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(scraper.scrape())


# -- Deel ATS -------------------------------------------------------------------

def _deel_posting(pid, title, state="published_basic", visible=True):
    return {
        "id": pid, "jobId": "j-" + pid, "title": title, "richtextDescription": "$44",
        "isCompensationVisible": visible, "createdAt": "2026-09-07T12:27:01.452Z",
        "job": {
            "workArrangementEnum": "HYBRID",
            "jobEmploymentTypes": [{"employmentType": {"name": "Full-time"}}],
            "jobLocations": [{"location": {"name": "Stockholm"}}, {"location": {"name": "London"}}],
            "currentCompensation": {"currencyIsoCode": "SEK", "minAmount": 600000, "maxAmount": 680000},
            "jobTeams": [], "jobDepartments": [{"department": {"name": "Engineering"}}],
        },
        "jobPostingPublications": [{"currentState": {"stateSlug": state}}],
    }


P1 = "11111111-1111-1111-1111-111111111111"
P2 = "22222222-2222-2222-2222-222222222222"
P3 = "33333333-3333-3333-3333-333333333333"


def test_decode_flight_joins_chunks():
    page = _flight_page({"x": 1})
    assert decode_flight(page) == '0:{"a":1}\n5:[{"x":1}]\n'


def test_deel_board_postings_parsed_from_flight():
    page = _flight_page(_deel_posting(P1, "Incident Manager"), _deel_posting(P1, "Incident Manager"),
                        _deel_posting(P2, "Analyst", visible=False),
                        _deel_posting(P3, "Draft role", state="unpublished"))
    requested = []

    async def fetch_html(url, params=None):
        requested.append(url)
        return page

    scraper = _no_db(FakeDeel())
    scraper.fetch_html = fetch_html
    result = asyncio.run(scraper.scrape())
    assert requested == ["https://jobs.deel.com/acme"]
    assert result.jobs_found == 2
    job = result.jobs[0]
    assert job.title == "Incident Manager"
    assert job.external_job_id == P1
    assert job.job_url == f"https://jobs.deel.com/acme/job-details/{P1}/overview"
    assert job.location == "Stockholm; London"
    assert job.department == "Engineering"
    assert job.employment_type == "Full-time"
    assert job.remote_type == "hybrid"
    assert job.posted_date.year == 2026 and job.posted_date.tzinfo is None
    assert (job.salary_min, job.salary_max) == (600000, 680000)
    assert (result.jobs[1].salary_min, result.jobs[1].salary_max) == (None, None)


def test_deel_careers_page_records_parsed():
    record = {"id": 0, "attributes": {
        "ashby_id": P1, "title": "Country Finance Manager", "team_name": "Country Finance",
        "location_name": "South Africa", "employment_type": "Full-time", "is_listed": True,
        "ashby_published_date": "2026-09-07T08:11:40.247Z",
        "external_link": f"https://jobs.deel.com/deel/job-details/{P1}/application",
        "all_locations": ["South Africa", "Kenya"],
    }}
    hidden = {"id": 1, "attributes": {**record["attributes"], "ashby_id": P2, "is_listed": False}}

    async def fetch_html(url, params=None):
        return _flight_page(record, hidden)

    scraper = _no_db(FakeDeel())
    scraper.fetch_html = fetch_html
    result = asyncio.run(scraper.scrape())
    assert result.jobs_found == 1
    job = result.jobs[0]
    assert job.job_url == f"https://jobs.deel.com/deel/job-details/{P1}/overview"
    assert job.location == "South Africa; Kenya"
    assert job.department == "Country Finance"
    assert job.posted_date.month == 9


def test_deel_page_without_flight_data_is_unexpected():
    async def fetch_html(url, params=None):
        return "<html><body>Maintenance</body></html>"

    scraper = _no_db(FakeDeel())
    scraper.fetch_html = fetch_html
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(scraper.scrape())
