"""IT-only staffing scrapers: category filters sent to the agency APIs, the per-title
services.it_roles filter applied to every listing page (before any detail fetch),
and MAX_JOBS counting IT postings only. Offline: recorded fixtures only."""
import asyncio
import copy

import pytest

from contracts.scrapers._base import StaffingScraper
from contracts.scrapers.akkodis import AkkodisScraper
from contracts.scrapers.allegis import ActalentScraper, TEKsystemsScraper
from contracts.scrapers.collabera import CollaberaScraper
from contracts.scrapers.cybercoders import CyberCodersScraper
from contracts.scrapers.experis import INDUSTRY_KEYS, ExperisScraper
from contracts.scrapers.insightglobal import InsightGlobalScraper
from contracts.scrapers.jobot import JobotScraper
from contracts.scrapers.judge import JudgeScraper
from contracts.scrapers.kforce import KforceScraper
from contracts.scrapers.motion import MotionRecruitmentScraper
from contracts.scrapers.randstad import RandstadScraper
from contracts.scrapers.roberthalf import RobertHalfScraper
from contracts.scrapers.yoh import YohScraper
from scrapers.base import ScraperConfig, ScraperType

import json
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "contracts" / "staffing"


def responses(slug):
    return json.loads((FIXTURES / f"{slug}.json").read_text())["responses"]


def offline(scraper, replies):
    """Answer scraper._http from `replies` in order (the last one repeats); record calls."""
    calls = []
    replies = list(replies)

    async def fake_http(method, url, **kw):
        calls.append({"method": method, "url": url, **kw})
        return replies[min(len(calls), len(replies)) - 1]

    async def no_network():
        raise AssertionError("test tried to open a network session")

    scraper._http = fake_http
    scraper.get_session = no_network
    scraper.MIN_INTERVAL = 0
    return calls

ALL = [TEKsystemsScraper, ActalentScraper, RandstadScraper, KforceScraper, RobertHalfScraper, ExperisScraper,
       JudgeScraper, MotionRecruitmentScraper, InsightGlobalScraper, JobotScraper, CollaberaScraper,
       AkkodisScraper, CyberCodersScraper, YohScraper]


def scrape(cls, replies=None, it_only=True):
    s = cls()
    s.IT_ONLY = it_only
    calls = offline(s, replies if replies is not None else responses(cls.config.company_slug))
    result = asyncio.run(s.scrape())
    assert result.success
    return s, result.jobs, calls


@pytest.mark.parametrize("cls", ALL, ids=[c.config.company_slug for c in ALL])
def test_non_it_postings_dropped_before_parsing(cls):
    s, jobs, _ = scrape(cls)
    off, everything, _ = scrape(cls, it_only=False)
    assert off.it_dropped == 0 and s.it_listed == off.it_listed > 0
    assert 0 < s.it_dropped < s.it_listed
    kept = {j.external_job_id for j in jobs}
    assert kept <= {j.external_job_id for j in everything}
    # what went missing was dropped by the IT filter (never more than it dropped)
    assert 0 < len(everything) - len(jobs) <= s.it_dropped
    for j in jobs:
        assert s.IT_ONLY and j.title


@pytest.mark.parametrize("cls,dropped,kept", [
    (TEKsystemsScraper, "Executive Administrative Assistant", None),
    (ActalentScraper, "Manufacturing Technician 3 (Swing Shift)", "Firmware Engineer"),
    (RandstadScraper, "Drone Flight Service Operator", None),
    (KforceScraper, "Warehouse Supervisor", None),
    (RobertHalfScraper, "Marketing Director", None),
    (ExperisScraper, "Medical Billing Specialist", "Software Quality Assurance Engineer"),
    (JudgeScraper, "Lead Mammography Tech", "AI Engineer"),
    (MotionRecruitmentScraper, "Recruiter", None),
    (InsightGlobalScraper, "HR Manager", "Technical Lead (.NET/AWS)"),
    (JobotScraper, "CNC Machinist", None),
    (CollaberaScraper, "Event Manager", None),
    (AkkodisScraper, "Truck washer/Jr. Technician", None),
    (CyberCodersScraper, "Tax Senior", None),
    (YohScraper, "Nurse Practitioner (General)", "Desktop Support Technician"),
])
def test_known_titles(cls, dropped, kept):
    s, jobs, _ = scrape(cls)
    titles = {j.title for j in jobs}
    assert dropped not in titles
    _, everything, _ = scrape(cls, it_only=False)
    assert dropped in {j.title for j in everything}
    if kept:
        assert kept in titles
    assert s.it_dropped >= 1


def test_phenom_requests_it_categories_only():
    _, _, calls = scrape(TEKsystemsScraper)
    cats = calls[1]["json_body"]["selected_fields"]["category"]
    assert "Customer Service" not in cats and {"Developer", "Helpdesk/Desktop", "Other"} <= set(cats)
    _, jobs, calls = scrape(ActalentScraper)
    assert calls[1]["json_body"]["selected_fields"]["category"] == [
        "Systems & Software", "Manufacturing, Mechanical, & Electrical"]
    assert all(j.department in ActalentScraper.CATEGORIES for j in jobs)


def test_experis_and_judge_categories():
    # Experis: whole board by default (the industry facet lost IT postings), filter optional
    _, _, calls = scrape(ExperisScraper)
    assert "industries" not in calls[0]["json_body"]["filter"]

    class ExperisIT(ExperisScraper):
        INDUSTRIES = ("Technology and IT", "Engineering")

    _, _, calls = scrape(ExperisIT)
    keys = [i["key"] for i in calls[0]["json_body"]["filter"]["industries"]]
    assert keys == [INDUSTRY_KEYS["Technology and IT"], INDUSTRY_KEYS["Engineering"]]
    # Judge: IT + Engineering at the API, the title filter drops non-IT engineering
    _, _, calls = scrape(JudgeScraper)
    assert calls[0]["json_body"]["payload"]["categories"] == ["InformationTechnology", "Engineering"]


def test_board_category_breaks_ties():
    s = ActalentScraper()
    it = {"title": "Engineer", "category": "Systems & Software"}
    mfg = {"title": "Engineer", "category": "Manufacturing, Mechanical, & Electrical"}
    assert s.is_it_posting(it) and not s.is_it_posting(mfg)
    # an explicit title wins over the category
    assert s.is_it_posting({"title": "Embedded Software Engineer",
                            "category": "Manufacturing, Mechanical, & Electrical"})


def test_ambiguous_default_per_board():
    # Randstad's listing is already its computer & mathematical category
    assert RandstadScraper().is_it_posting({"title": "Consultant"})
    assert not JobotScraper().is_it_posting({"title": "Consultant"})


def _rh_page(titles, found, page_no):
    page = copy.deepcopy(responses("roberthalf")[0])
    template = page["jobs"][0]
    page["jobs"] = [dict(template, jobtitle=t, unique_job_number=f"id-{page_no}-{i}", functional_role="", skills="")
                    for i, t in enumerate(titles)]
    page["found"] = found
    return page


def test_paging_continues_past_non_it_and_cap_counts_it_only():
    non_it = ["Registered Nurse", "Warehouse Associate", "Accountant", "Cashier"]
    it = ["Java Developer", "Data Engineer", "Help Desk Technician", "Network Administrator"]
    replies = [_rh_page(non_it, 12, 1), _rh_page(it, 12, 2), _rh_page(it[:2] + non_it[:2], 12, 3)]
    s, jobs, calls = scrape(RobertHalfScraper, replies)
    # page 1 had nothing IT but paging went on until the listing's end (12 listed)
    assert len(calls) == 3 and s.it_listed == 12 and s.it_dropped == 6
    assert sorted(j.title for j in jobs) == sorted(it + it[:2])

    class Capped(RobertHalfScraper):
        MAX_JOBS = 3

    s, jobs, calls = scrape(Capped, replies)
    # the cap is on IT postings: page 1 (0 IT) does not stop paging, page 2 (4 IT) does
    assert len(calls) == 2 and len(jobs) == 3


class _Detail(StaffingScraper):
    """A board that fetches a detail page per posting: only IT postings may reach it."""
    config = ScraperConfig(company_slug="detail-staffing", company_name="Detail Staffing",
                           careers_url="https://example.com", scraper_type=ScraperType.HTTP)
    AGENCY_NAME = "Detail Staffing"
    detail_calls: list = []

    async def fetch_raw(self):
        page = self.take_it([{"title": "Registered Nurse", "id": "1"}, {"title": "DevOps Engineer", "id": "2"}])
        for raw in page:
            self.detail_calls.append(raw["id"])
        return page

    def parse_job(self, raw):
        return self.make_job(title=raw["title"], location="Austin, TX", job_url=f"https://x/{raw['id']}",
                             external_job_id=raw["id"])


def test_detail_fetch_only_for_it_postings():
    _Detail.detail_calls = []
    s = _Detail()
    offline(s, [{}])
    jobs = asyncio.run(s.scrape()).jobs
    assert _Detail.detail_calls == ["2"] and [j.title for j in jobs] == ["DevOps Engineer"]
    assert (s.it_listed, s.it_dropped) == (2, 1)


def test_it_only_can_be_switched_off():
    s, jobs, _ = scrape(JobotScraper, it_only=False)
    assert s.it_dropped == 0 and len(jobs) > 1


def _experis_page(n, total):
    page = copy.deepcopy(responses("experis")[0])
    tpl = next(j for j in page["jobsItems"] if j.get("domain") == "Technology and IT")
    page["jobsItems"] = [dict(tpl, jobID=f"{n}-{i}", jobTitle="Java Developer") for i in range(2)]
    page["filters"]["totalCount"] = total
    return page


def _flaky(scraper, pages, fail_on):
    """pages served in order; the calls listed in fail_on answer HTTP 502 instead."""
    import aiohttp
    calls = []

    async def fake_http(method, url, **kw):
        calls.append(kw)
        if len(calls) in fail_on:
            raise aiohttp.ClientResponseError(request_info=None, history=(), status=502)
        return pages.pop(0)

    scraper._http = fake_http
    scraper.MIN_INTERVAL = 0
    scraper.RETRY_DELAY = 0
    return calls


def test_experis_retries_a_502_page_then_continues():
    s = ExperisScraper()
    calls = _flaky(s, [_experis_page(1, 6), _experis_page(2, 6), _experis_page(3, 6)], fail_on={2})
    jobs = asyncio.run(s.scrape()).jobs
    assert len(calls) == 4 and len(jobs) == 6


def test_experis_keeps_what_it_has_after_repeated_502s():
    s = ExperisScraper()
    _flaky(s, [_experis_page(1, 6)], fail_on={2, 3, 4})
    assert len(asyncio.run(s.scrape()).jobs) == 2
