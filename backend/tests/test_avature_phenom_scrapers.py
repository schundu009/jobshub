"""Offline tests for the Avature, Phenom and Capgemini scrapers (no network)."""
import asyncio
import json
from datetime import datetime

import pytest

from scrapers.base import (
    HTTPScraper,
    ScraperConfig,
    ScraperType,
    UnexpectedResponseError,
)
from scrapers.enterprise.avature_scrapers import (
    AvatureMixin,
    LululemonScraper,
    SiemensScraper,
)
from scrapers.enterprise.capgemini import CapgeminiScraper
from scrapers.enterprise.phenom_scrapers import (
    BAESystemsScraper,
    DHLScraper,
    FranklinTempletonScraper,
    PhenomMixin,
    _parse_phenom_date,
    parse_phenom_ddo,
)
from scrapers.registry import ScraperRegistry


def _cfg(slug):
    return ScraperConfig(company_slug=slug, company_name=slug.title(),
                         careers_url="https://example.com", scraper_type=ScraperType.HTTP)


# ---------------------------------------------------------------- Avature ---

def _lulu_card(job_id, title="Educator", loc="United States of America · Georgia · Athens"):
    return f"""
    <article class="article article--result">
      <div class="article__header"><div class="article__header__text">
        <h3 class="article__header__text__title">
          <a href="https://careers.example.com/en_US/careers/JobDetail/{title}-Slug/{job_id}">
            {title}
          </a>
        </h3>
        <div class="article__header__text__subtitle"><span>{loc}</span></div>
      </div>
      <div class="article__header__actions">
        <a class="apply" href="https://careers.example.com/en_US/careers/ApplicationMethods?jobId={job_id}">Apply</a>
      </div></div>
    </article>"""


def _siemens_card(job_id):
    return f"""
    <article class="article article--result 1">
      <h3 class="article__header__text__title">
        <a class="link" href="https://jobs.example.com/en_US/externaljobs/JobDetail/{job_id}">Research Scientist</a>
      </h3>
      <div class="article__header__text__subtitle">
        <span class="list-item-location"><span class="list-item-jobCity">Suzhou</span><span class="separator">, </span><span class="list-item-jobState">Jiangsu Sheng</span><span class="separator">, </span><span class="list-item-jobCountry">China</span></span>
        <span class="separator">&nbsp;&#8226;&nbsp;</span> <span class="list-item-jobId">Job ID: {job_id}</span>
        <span class="separator">&nbsp;&#8226;&nbsp;</span> <span class="list-item-family">Research &amp; Development</span>
      </div>
    </article>"""


def _avature_page(cards, next_param="folderOffset", next_offset=None):
    nxt = ""
    if next_offset is not None:
        nxt = (f'<li class="list-controls__pagination__item paginationNextLink">'
               f'<a href="https://jobs.example.com/SearchJobs/?folderRecordsPerPage=2&amp;{next_param}={next_offset}">Next</a></li>')
    return f"<html><body>{''.join(cards)}<ul>{nxt}</ul></body></html>"


class FakeAvature(AvatureMixin, HTTPScraper):
    config = _cfg("fakeavature")
    PORTAL_URL = "https://jobs.example.com/en_US/externaljobs"
    CONCURRENCY = 2


def _mock_avature(scraper, first_html, pages_by_offset, calls):
    async def fetch_html(url, params=None):
        calls.append(("first", url, params))
        return first_html

    async def fetch_page(offset_param, offset):
        calls.append((offset_param, offset))
        return pages_by_offset.get(offset, _avature_page([]))

    scraper.fetch_html = fetch_html
    scraper._fetch_page = fetch_page
    return scraper


def test_avature_lululemon_card_parsing_reverses_location():
    s = LululemonScraper()
    rows = s._extract_rows(_avature_page([_lulu_card(64230, "Guest-Lead")]))
    assert len(rows) == 1
    job = s.parse_job(rows[0])
    assert job.external_job_id == "64230"
    assert job.title == "Guest-Lead"
    assert job.location == "Athens, Georgia, United States of America"
    assert job.job_url == "https://careers.example.com/en_US/careers/JobDetail/Guest-Lead-Slug/64230"


def test_avature_siemens_card_parsing_location_and_department():
    s = SiemensScraper()
    job = s.parse_job(s._extract_rows(_avature_page([_siemens_card(524277)]))[0])
    assert job.external_job_id == "524277"
    assert job.location == "Suzhou, Jiangsu Sheng, China"
    assert job.department == "Research & Development"
    assert job.job_url.endswith("/externaljobs/JobDetail/524277")


def test_avature_paginates_with_detected_offset_param_and_page_size():
    first = _avature_page([_siemens_card(1), _siemens_card(2)], next_offset=2)
    pages = {
        2: _avature_page([_siemens_card(3), _siemens_card(4)]),
        4: _avature_page([_siemens_card(5)]),
        # offset 6 -> empty page ends the scrape
    }
    calls = []
    result = asyncio.run(_mock_avature(FakeAvature(), first, pages, calls).scrape())
    assert [j.external_job_id for j in result.jobs] == ["1", "2", "3", "4", "5"]
    page_calls = [c for c in calls if c[0] != "first"]
    assert page_calls[:2] == [("folderOffset", 2), ("folderOffset", 4)]
    assert all(c[0] == "folderOffset" for c in page_calls)


def test_avature_stops_when_offset_is_ignored_and_pages_repeat():
    first = _avature_page([_siemens_card(1), _siemens_card(2)], next_offset=2)
    repeat = _avature_page([_siemens_card(1), _siemens_card(2)])
    calls = []
    s = _mock_avature(FakeAvature(), first, {o: repeat for o in range(0, 100, 2)}, calls)
    result = asyncio.run(s.scrape())
    assert result.jobs_found == 2
    assert len(calls) <= 1 + FakeAvature.CONCURRENCY


def test_avature_single_page_without_next_link():
    calls = []
    s = _mock_avature(FakeAvature(), _avature_page([_siemens_card(9)]), {}, calls)
    result = asyncio.run(s.scrape())
    assert result.jobs_found == 1
    assert calls == [("first", "https://jobs.example.com/en_US/externaljobs/SearchJobs/", None)]


def test_avature_respects_max_jobs():
    first = _avature_page([_siemens_card(1), _siemens_card(2)], next_offset=2)
    pages = {o: _avature_page([_siemens_card(o + 1), _siemens_card(o + 2)]) for o in range(2, 1000, 2)}

    class Capped(FakeAvature):
        MAX_JOBS = 6

    result = asyncio.run(_mock_avature(Capped(), first, pages, []).scrape())
    assert 6 <= result.jobs_found < 10


def test_avature_page_without_cards_raises():
    s = _mock_avature(FakeAvature(), "<html>maintenance</html>", {}, [])
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(s.scrape())


# ----------------------------------------------------------------- Phenom ---

def _phenom_job(n, title="Logistics Coordinator"):
    return {
        "jobId": f"AV-{n}", "reqId": f"AV-{n}", "jobSeqNo": f"SEQ{n}", "title": title,
        "location": "San Francisco, California, United States of America",
        "multi_category": ["Operations"], "postedDate": "2026-07-29T21:36:55.608+0000",
        "type": "Full-time",
    }


def _phenom_html(jobs, total):
    ddo = {"siteConfig": {}, "eagerLoadRefineSearch": {
        "status": 200, "hits": len(jobs), "totalHits": total, "data": {"jobs": jobs}}}
    return (
        '<script>var phApp = phApp || {"widgetApiEndpoint":"x","country":"global",'
        '"deviceType":"desktop","locale":"en_global","refNum":"ACME1","pageName":"search-results",'
        '"pageId":"page17"};'
        f"phApp.ddo = {json.dumps(ddo)}; phApp.experimentData = {{}};</script>"
    )


class FakePhenom(PhenomMixin, HTTPScraper):
    config = _cfg("fakephenom")
    SITE_URL = "https://careers.example.com/global/en"
    PAGE_SIZE = 2


def _mock_phenom(scraper, html, widget, calls, html_pages=None):
    async def fetch_html(url, params=None):
        calls.append(("html", url, params))
        if params and html_pages is not None:
            return html_pages[int(params["from"])]
        return html

    async def fetch_json(url, method="GET", json_data=None, **_):
        calls.append(("json", url, json_data))
        return widget(json_data)

    scraper.fetch_html = fetch_html
    scraper.fetch_json = fetch_json
    return scraper


def test_phenom_ddo_and_date_parsing():
    ddo = parse_phenom_ddo(_phenom_html([_phenom_job(1)], 1))
    assert ddo["eagerLoadRefineSearch"]["totalHits"] == 1
    assert parse_phenom_ddo("<html></html>") == {}
    assert _parse_phenom_date("2026-07-29T21:36:55.608+0000") == datetime(2026, 7, 29, 21, 36, 55, 608000)
    assert _parse_phenom_date("") is None


def test_phenom_parse_job_builds_public_url():
    job = FakePhenom().parse_job(_phenom_job(366804, "Admin Assistant (A4)"))
    assert job.job_url == "https://careers.example.com/global/en/job/AV-366804/Admin-Assistant-A4"
    assert job.external_job_id == "AV-366804"
    assert job.department == "Operations"
    assert job.posted_date == datetime(2026, 7, 29, 21, 36, 55, 608000)
    assert FakePhenom().parse_job({"title": "No id"}) is None


def test_phenom_widgets_pagination_uses_page_settings_and_clamps_size():
    all_jobs = [_phenom_job(n) for n in range(5)]

    def widget(body):
        chunk = all_jobs[body["from"]:body["from"] + body["size"]]
        return {"refineSearch": {"status": 200, "totalHits": 5, "data": {"jobs": chunk}}}

    calls = []
    s = _mock_phenom(FakePhenom(), _phenom_html(all_jobs[:2], 5), widget, calls)
    result = asyncio.run(s.scrape())
    assert [j.external_job_id for j in result.jobs] == [f"AV-{n}" for n in range(5)]
    posts = [c for c in calls if c[0] == "json"]
    assert posts[0][1] == "https://careers.example.com/widgets"
    body = posts[0][2]
    assert (body["refNum"], body["lang"], body["country"], body["pageId"]) == ("ACME1", "en_global", "global", "page17")
    assert body["ddoKey"] == "refineSearch"
    # never asks past totalHits (Phenom answers such pages with no jobs)
    assert [(b["from"], b["size"]) for _, _, b in posts] == [(0, 2), (2, 2), (4, 1)]


def test_phenom_falls_back_to_html_paging_when_widgets_fail():
    jobs = [_phenom_job(n) for n in range(3)]

    def widget(body):
        raise RuntimeError("403 Forbidden")

    html_pages = {2: _phenom_html(jobs[2:], 3)}
    calls = []
    s = _mock_phenom(FakePhenom(), _phenom_html(jobs[:2], 3), widget, calls, html_pages)
    result = asyncio.run(s.scrape())
    assert result.jobs_found == 3
    assert ("html", "https://careers.example.com/global/en/search-results", {"from": "2", "s": "1"}) in calls


def test_phenom_missing_ddo_raises():
    s = _mock_phenom(FakePhenom(), "<html>blocked</html>", lambda b: {}, [])
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(s.scrape())


# -------------------------------------------------------------- Capgemini ---

def _cg_job(n, source="SAP_BTP"):
    return {"id": f"{n}-en_US_SAPBTP", "ref": f"{n}-en_US", "source": source, "title": "Quality Engineer",
            "location": "Aguascalientes", "professional_communities": "Quality Engineering & Testing",
            "brand": "Capgemini", "contract_type": "Permanent", "description": "<p>x</p>",
            "updated_at": "2026-09-30T00:38:19.000Z"}


def test_capgemini_parse_job_url_and_fields():
    job = CapgeminiScraper().parse_job(_cg_job(540483))
    assert job.job_url == "https://www.capgemini.com/jobs/540483-en_US+sap_btp"
    assert job.external_job_id == "540483-en_US_SAPBTP"
    assert job.department == "Quality Engineering & Testing"
    assert job.posted_date is None  # updated_at is a re-index time, not a posting date
    gh = CapgeminiScraper().parse_job({**_cg_job(1), "ref": "4100955101", "source": "GREENHOUSEGERMANINVENT"})
    assert gh.job_url == "https://www.capgemini.com/jobs/4100955101+greenhousegermaninvent"
    assert CapgeminiScraper().parse_job({"title": "x"}) is None


def test_capgemini_paginates_until_count():
    class Small(CapgeminiScraper):
        PAGE_SIZE = 2

    jobs = [_cg_job(n) for n in range(5)]
    calls = []

    async def fetch_json(url, params=None, **_):
        calls.append(params)
        start = (params["page"] - 1) * params["size"]
        return {"count": 5, "data": jobs[start:start + params["size"]]}

    s = Small()
    s.url_override = CapgeminiScraper.API_URL
    s.fetch_json = fetch_json
    result = asyncio.run(s.scrape())
    assert result.jobs_found == 5
    assert [p["page"] for p in calls] == [1, 2, 3]


def test_capgemini_unexpected_shape_raises():
    async def fetch_json(url, params=None, **_):
        return {"error": "nope"}

    s = CapgeminiScraper()
    s.url_override = CapgeminiScraper.API_URL
    s.fetch_json = fetch_json
    with pytest.raises(UnexpectedResponseError):
        asyncio.run(s.scrape())


# --------------------------------------------------------------- Registry ---

@pytest.mark.parametrize("slug,cls,name", [
    ("siemens", SiemensScraper, "Siemens"),
    ("lululemon", LululemonScraper, "Lululemon"),
    ("dhl", DHLScraper, "DHL"),
    ("bae", BAESystemsScraper, "BAE Systems"),
    ("franklintempleton", FranklinTempletonScraper, "Franklin Templeton"),
    ("capgemini", CapgeminiScraper, "Capgemini"),
])
def test_replacement_scrapers_registered(slug, cls, name):
    assert ScraperRegistry.get(slug) is cls
    assert cls.config.company_name == name
    assert cls.config.enabled
    assert "myworkdayjobs" not in cls.config.careers_url
