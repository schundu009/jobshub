"""On-demand description extractors (contracts.scrapers.<source>.fetch_description).
Offline: contracts.descriptions.polite_get is replaced by recorded, PII-masked pages
(tests/fixtures/contracts/descriptions/, captured 2026-09-29)."""
import json
from pathlib import Path

import pytest

import contracts.descriptions as descriptions
from contracts.scrapers import akkodis, collabera, insightglobal, motion

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "contracts" / "descriptions"


class FakeResponse:
    def __init__(self, text, status_code=200):
        self.text = text
        self.content = text.encode()
        self.status_code = status_code

    def json(self):
        return json.loads(self.text)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


@pytest.fixture
def pages(monkeypatch):
    """Map URL -> body for polite_get; records requested URLs."""
    served, calls = {}, []

    def fake_get(url, timeout=descriptions.FETCH_TIMEOUT, **kw):
        calls.append({"url": url, **kw})
        if url not in served:
            raise AssertionError(f"unexpected fetch {url}")
        return FakeResponse(served[url])

    monkeypatch.setattr(descriptions, "polite_get", fake_get)
    return served, calls


def test_collabera(pages):
    served, calls = pages
    served["https://www.collabera.com/job-description/?post=371974"] = (FIX / "collabera_detail.html").read_text()
    html, text = collabera.fetch_description("https://www.collabera.com/job-description/?post=371974")
    assert "RF Antenna Test Engineer" in text and "VNA, spectrum analyzer" in text
    assert "Pay Range" in text and "<li>" in html
    # the recruiter card next to the description is not read
    assert "Recruiter" not in text and "@" not in html
    assert calls[0]["url"].endswith("?post=371974")


def test_collabera_other_page_is_not_a_posting(pages):
    served, _ = pages
    # An unknown ?post= renders a generic page without this posting's apply form.
    body = (FIX / "collabera_detail.html").read_text().replace("qsPostId=371974", "qsPostId=")
    served["https://www.collabera.com/job-description/?post=42"] = body
    assert collabera.fetch_description("https://www.collabera.com/job-description/?post=42") == (None, None)
    assert collabera.parse_collabera_description("<html><body>nothing</body></html>") == (None, None)


def test_insightglobal_uses_the_public_detail_json(pages):
    served, calls = pages
    rid = "eb6ad967-ef43-45f2-935f-4d5d4be1f437"
    served[f"https://insightglobal.com/all/jobs/{rid}"] = (FIX / "insightglobal_detail.json").read_text()
    html, text = insightglobal.fetch_description(f"https://insightglobal.com/jobs/{rid}")
    assert "C#/.NET" in text and "Required Skills & Experience" in text
    assert "\n" in text and "<br>" in html
    assert calls[0]["headers"]["Accept"] == "application/json"


def test_insightglobal_no_description(pages):
    served, _ = pages
    served["https://insightglobal.com/all/jobs/abcdef12-0000"] = json.dumps({"requisitionId": "abcdef12-0000"})
    assert insightglobal.fetch_description("https://insightglobal.com/jobs/abcdef12-0000") == (None, None)


def test_akkodis_jsonld(pages):
    served, _ = pages
    url = ("https://www.akkodis.com/en-us/careers/jobs/full-stack-data-engineer-dearborn-michigan/"
           "us_en_6_971649_1648133")
    served[url] = (FIX / "akkodis_detail.html").read_text()
    html, text = akkodis.fetch_description(url)
    assert text.startswith("Akkodis is seeking a Full Stack Data Engineer")
    assert "<p>" in html and "&#60;" not in html


def test_motion_rsc_detail(pages):
    served, _ = pages
    url = "https://motionrecruitment.com/tech-jobs/irving/contract/network-asset-management-analyst/887949"
    served[url] = (FIX / "motion_detail.html").read_text()
    html, text = motion.fetch_description(url)
    assert text.startswith("Outstanding long-term contract opportunity")
    assert len(text) > 500


@pytest.mark.parametrize("module,url", [
    (collabera, "https://evil.example.com/job-description/?post=1"),
    (collabera, "https://www.collabera.com/job-description/?post=abc"),
    (insightglobal, "https://insightglobal.com/jobs/"),
    (insightglobal, "https://example.com/jobs/7ca97d65-abf3-40b1-a0b1-702c5a388940"),
    (akkodis, "https://www.akkodis.com/en-us/about"),
    (motion, "https://motionrecruitment.com/tech-jobs"),
    (motion, None),
])
def test_foreign_or_non_posting_urls_are_not_fetched(pages, module, url):
    _, calls = pages
    assert module.fetch_description(url) == (None, None)
    assert calls == []


def test_registered_sources_have_extractors():
    for source, module in descriptions.DESCRIPTION_SOURCES.items():
        fn = descriptions._fetcher(source)
        assert callable(fn), (source, module)
