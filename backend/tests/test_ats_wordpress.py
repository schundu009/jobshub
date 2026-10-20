"""WordPress REST / WP Job Manager type (scrapers.ats.wordpress)."""
import asyncio
import json
from pathlib import Path

from scrapers.board_scraper import api_url, board_careers_url, build_scraper_class

FIX = Path(__file__).parent / "fixtures" / "ats" / "wordpress"


def scraper(board):
    return build_scraper_class({"slug": "wpco", "company_name": "WP Co", "ats": "wordpress", "board": board, "careers_url": None})()


def test_board_validation_and_urls():
    url = api_url("wordpress", "bhsg.com/jobs/job-listings")
    assert url.startswith("https://bhsg.com/jobs/wp-json/wp/v2/job-listings?per_page=100&page=1&_embed=wp:term")
    assert api_url("wordpress", "www.excelonsolutions.com/posts?categories=5").endswith("&categories=5")
    assert api_url("wordpress", "storm2.com/jm-ajax") == "https://storm2.com/jm-ajax/get_listings/"
    assert board_careers_url("wordpress", "bhsg.com/jobs/job-listings") == "https://bhsg.com/jobs/"
    assert api_url("wordpress", "rgp.com") is None
    assert api_url("wordpress", "https://rgp.com/rgp_job_opening") is None


def test_rest_scrape_and_parse():
    s = scraper("rgp.com/rgp_job_opening")

    async def request(method, url, read, **_):
        class Response:
            headers = {"X-WP-TotalPages": "1"}

            async def text(self):
                return "﻿" + (FIX / "rest.json").read_text()  # some sites send a BOM
        return await read(Response())
    s._request = request
    result = asyncio.run(s.scrape())
    assert result.success and result.complete and len(result.jobs) == 3
    rgp, heart, storm = result.jobs
    # taxonomies: city, state, country; Full time from rgp_full_or_part_time, not rgp_job_record_type
    assert rgp.location == "Arlington, Texas, United States" and rgp.employment_type_raw == "Full time"
    assert rgp.job_url == "https://rgp.com/careers/job-openings/lovable-system-administrator/"
    # Matador: "Hybrid" + "Phoenix" terms; the posting's own "Location: Phoenix, AZ" wins
    assert heart.location == "Phoenix, AZ" and heart.employment_type_raw == "Contract"
    # WP Job Manager meta; sector names filed as job types are not work types
    assert storm.location == "California, United States" and storm.employment_type_raw != "Payments"
    assert (storm.pay_rate_min, storm.pay_period, storm.salary_min) == (180000.0, "year", 180000)


def test_jm_ajax_skips_expired():
    s = scraper("example-wpjm.com/jm-ajax")
    posted = []

    async def request(method, url, read, data=None, **_):
        posted.append((method, url, data))
        return json.loads((FIX / "jm_listings.json").read_text())
    s._request = request
    result = asyncio.run(s.scrape())
    assert posted[0][0] == "POST" and posted[0][2]["per_page"] == "100"
    assert len(result.jobs) == 1 and result.complete
    job = result.jobs[0]
    assert job.title == "Senior Software Engineer" and job.location == "Austin, Texas"
    assert job.job_url == "https://example-wpjm.com/job/senior-software-engineer/" and job.external_job_id == "21178"
    assert job.employment_type_raw == "Direct Hire" and job.employment_type == "full-time"
