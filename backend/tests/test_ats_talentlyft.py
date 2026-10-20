import asyncio
import json
from pathlib import Path

from scrapers.board_scraper import api_url, board_careers_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats"


def fixture(name):
    text = (FIX / name).read_text()
    return json.loads(text) if name.endswith(".json") else text


def scraper(ats, board, slug="atsco"):
    cls = build_scraper_class({"slug": slug, "company_name": "Ats Co", "ats": ats, "board": board, "careers_url": None})
    assert cls is not None
    return cls()

def test_talentlyft_joblist():
    assert api_url("talentlyft", "kpmg-bulgaria") == "https://kpmg-bulgaria.talentlyft.com/JobList"
    assert api_url("talentlyft", "Bad_Sub") is None
    s = scraper("talentlyft", "kpmg-bulgaria")

    async def request(method, url, read, params=None, headers=None, **_):
        assert headers == {"X-Requested-With": "XMLHttpRequest"} and params["subdomain"] == "kpmg-bulgaria"
        return fixture("talentlyft/joblist.html")
    s._request = request
    result = asyncio.run(s.scrape())
    assert result.complete
    job = result.jobs[0]
    assert job.title == "Accounting and Tax Compliance Advisor" and job.external_job_id == "223493"
    assert job.location == "Sofia/Varna, Bulgaria" and job.remote_type == "hybrid"
    assert job.job_url == "https://kpmg-bulgaria.talentlyft.com/jobs/accounting-and-tax-compliance-advisor-cdf3"
