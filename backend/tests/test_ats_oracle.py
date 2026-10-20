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


def test_oracle_board():
    board = "ecge.fa.us2.oraclecloud.com/CX_1003"
    assert api_url("oracle", board) == \
        "https://ecge.fa.us2.oraclecloud.com/hcmRestApi/resources/latest/recruitingCEJobRequisitions"
    assert board_careers_url("oracle", board) == \
        "https://ecge.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1003/jobs"
    assert api_url("oracle", "ecge.fa.us2.oraclecloud.com") is None
    assert api_url("oracle", "ecge.fa.us2.oraclecloud.com/CX 1") is None
    s = scraper("oracle", board)
    assert (s.HCM_HOST, s.SITE_NUMBER) == ("ecge.fa.us2.oraclecloud.com", "CX_1003")
    job = s.parse_job({"Id": "2026208", "Title": "Business Analyst", "PrimaryLocation": "Long Beach, CA, United States",
                       "PostedDate": "2026-10-19"})
    assert job.job_url == "https://ecge.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1003/job/2026208"
