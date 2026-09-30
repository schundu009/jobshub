"""
Replacements for scrapers whose old boards died (verified 2026-09-29).

- keybank: Workday tenant is keybank.wd5 (not key.wd5), site External_Career_Site.
- redfin:  Redfin (acquired by Rocket) posts on Rocket's Workday tenant
           quickenloans.wd5/rocket_careers; filtered by the hiringCompany facet
           "Redfin Corporation". careers.redfin.com redirects to careers.rocket.com.
- lennar:  careers.lennar.com (custom site) - server-rendered result tables at
           /api/requisitions/search/en?page=N, 10 per page.
- walmart: careers.walmart.com (custom Next.js site). Its only public search is
           the "job search assistant" GraphQL persisted query; with
           direct_search=true and refined_query=<keywords> it runs a plain
           keyword search without the LLM. 10 jobs per page, ~50k postings
           (mostly store/field roles), so we sweep a list of professional
           keywords instead of the whole board.
"""

import asyncio
import json
import re
import time
import uuid
from datetime import datetime
from typing import List, Optional

from bs4 import BeautifulSoup

from scrapers.base import (
    HTTPScraper,
    ScrapedJob,
    ScraperConfig,
    ScraperType,
    ScrapeResult,
    UnexpectedResponseError,
)
from scrapers.custom.remaining_scrapers import WorkdayMixin
from scrapers.registry import ScraperRegistry


# ---------------------------------------------------------------------------
# Workday (KeyBank, Redfin)
# ---------------------------------------------------------------------------

class WorkdayFacetMixin(WorkdayMixin):
    """WorkdayMixin that sends fixed appliedFacets (e.g. one hiring company)."""

    APPLIED_FACETS: dict = {}

    async def fetch_json(self, url, method="GET", params=None, json_data=None, **kwargs):
        if method == "POST" and isinstance(json_data, dict) and "appliedFacets" in json_data:
            json_data = {**json_data, "appliedFacets": dict(self.APPLIED_FACETS)}
        return await super().fetch_json(url, method=method, params=params, json_data=json_data, **kwargs)


@ScraperRegistry.register(category="enterprise")
class KeyBankWorkdayScraper(WorkdayMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="keybank",
        company_name="KeyBank",
        careers_url="https://keybank.wd5.myworkdayjobs.com/External_Career_Site",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=20,
    )
    API_URL = "https://keybank.wd5.myworkdayjobs.com/wday/cxs/keybank/External_Career_Site/jobs"


@ScraperRegistry.register(category="other")
class RedfinRocketWorkdayScraper(WorkdayFacetMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="redfin",
        company_name="Redfin",
        careers_url="https://careers.rocket.com/us/en/search-results?keywords=redfin",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=20,
    )
    API_URL = "https://quickenloans.wd5.myworkdayjobs.com/wday/cxs/quickenloans/rocket_careers/jobs"
    # Workday "Company" facet value for "Redfin Corporation"
    APPLIED_FACETS = {"hiringCompany": ["768c36a8181b10014e52c9cef6400000"]}


# ---------------------------------------------------------------------------
# Lennar (careers.lennar.com)
# ---------------------------------------------------------------------------

_LENNAR_JOB_RE = re.compile(r"/job/(\d+)/")


@ScraperRegistry.register(category="enterprise")
class LennarCareersScraper(HTTPScraper):
    config = ScraperConfig(
        company_slug="lennar",
        company_name="Lennar Homes",
        careers_url="https://careers.lennar.com/search",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=150,
    )
    API_URL = "https://careers.lennar.com/api/requisitions/search/en"
    MAX_PAGES = 150
    MAX_JOBS = 1500
    TIME_BUDGET_SECONDS = 75

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS
        raw_jobs: List[dict] = []
        seen = set()
        pages = 0
        for page in range(1, self.MAX_PAGES + 1):
            html = await self.fetch_html(self.API_URL, params={"page": str(page)})
            rows = self.parse_results_page(html)
            if page == 1 and not rows and "job-title" not in html:
                raise UnexpectedResponseError("no Lennar result table on page 1")
            new_rows = [r for r in rows if r["id"] not in seen]
            if not new_rows:
                break
            pages += 1
            seen.update(r["id"] for r in new_rows)
            raw_jobs.extend(new_rows)
            if len(raw_jobs) >= self.MAX_JOBS or loop.time() > deadline:
                self.logger.info(f"Lennar: stopping at {len(raw_jobs)} jobs (cap/time budget)")
                break
            await asyncio.sleep(0.1)
        jobs = self.parse_all(raw_jobs)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=pages)

    @staticmethod
    def parse_results_page(html: str) -> List[dict]:
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for tr in soup.select("tbody tr"):
            link = tr.select_one("td.job-title a[href]")
            if not link:
                continue
            m = _LENNAR_JOB_RE.search(link["href"])
            if not m:
                continue
            loc_td = tr.select_one("td.job-location")
            if loc_td:
                for svg in loc_td.find_all("svg"):
                    svg.decompose()
            date_td = tr.select_one("td.job-date")
            out.append({
                "id": m.group(1),
                "title": link.get_text(" ", strip=True),
                "url": link["href"].split("?", 1)[0],
                "location": loc_td.get_text(" ", strip=True) if loc_td else "",
                "date": date_td.get_text(" ", strip=True) if date_td else "",
            })
        return out

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = self.clean_text(raw.get("title"))
            if not title:
                return None
            return ScrapedJob(
                title=title,
                location=raw.get("location", ""),
                job_url=raw["url"],
                external_job_id=raw["id"],
                posted_date=self.parse_date(raw.get("date")),
            )
        except Exception as e:
            self.logger.error(f"Error parsing Lennar job: {e}")
            return None


# ---------------------------------------------------------------------------
# Walmart (careers.walmart.com)
# ---------------------------------------------------------------------------

@ScraperRegistry.register(category="enterprise")
class WalmartCareersScraper(HTTPScraper):
    config = ScraperConfig(
        company_slug="walmart",
        company_name="Walmart",
        careers_url="https://careers.walmart.com/us/en/results",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=200,
        request_timeout=20,
        headers={
            "Origin": "https://careers.walmart.com",
            "Referer": "https://careers.walmart.com/us/en/results",
        },
    )
    API_URL = "https://careers.walmart.com/api/graphql"
    INIT_URL = "https://careers.walmart.com/api/init"
    # Persisted query "ChatBasedJobSearchQuery" from the site's JS bundle
    QUERY_ID = "b0467c1f-f578-4261-9280-0ea4614f251c"
    JOB_URL = "https://careers.walmart.com/us/en/jobs/{job_id}"

    # Keyword sweep over corporate/professional roles (the full board is ~50k
    # mostly hourly store postings, 10 per request).
    KEYWORDS = [
        "software engineer", "engineer", "data", "machine learning", "product manager",
        "program manager", "analyst", "designer", "security", "cloud",
        "finance", "accounting", "marketing", "merchandising", "supply chain",
        "operations manager", "people partner", "legal", "pharmacist", "director",
    ]
    PAGES_PER_KEYWORD = 5
    MAX_JOBS = 1500
    # Leaves room for requests still in flight (request_timeout=20s) at the deadline.
    TIME_BUDGET_SECONDS = 50
    CONCURRENCY = 4

    def _search_body(self, keyword: str, page: int) -> dict:
        return {
            "queryId": self.QUERY_ID,
            "variables": {
                "chatRequest": {
                    "messages": [{"role": "user", "content": [{"type": "text", "text": ""}]}],
                    "thread_id": f"S-{int(time.time() * 1000)}-{uuid.uuid4()}",
                    "channel": "job_search",
                    "context": {
                        "job_search_context": {
                            "locale": "en_US",
                            "sort": "relevance",
                            "active_tab": "jobs",
                            "management_levels": [],
                            "content_page": 0,
                            "future_roles_page": 0,
                            "job_page": page,
                            "direct_search": True,
                            "refined_query": keyword,
                        }
                    },
                }
            },
            "headers": {},
        }

    @staticmethod
    def extract_jobs(data: dict) -> List[dict]:
        """Pull artifact.jobs out of a jobSearchAssistant GraphQL response."""
        if not isinstance(data, dict):
            raise UnexpectedResponseError(f"expected dict, got {type(data).__name__}")
        assistant = (data.get("data") or {}).get("jobSearchAssistant")
        if not isinstance(assistant, dict):
            raise UnexpectedResponseError(
                f"no data.jobSearchAssistant (errors={str(data.get('errors'))[:200]})"
            )
        for msg in assistant.get("tool_messages") or []:
            artifact = msg.get("artifact")
            if isinstance(artifact, str):
                try:
                    artifact = json.loads(artifact)
                except ValueError:
                    continue
            if isinstance(artifact, dict) and isinstance(artifact.get("jobs"), list):
                return artifact["jobs"]
        raise UnexpectedResponseError("no artifact.jobs in jobSearchAssistant response")

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS
        # Sets the session cookies the GraphQL gateway expects.
        try:
            await self.fetch_json(self.INIT_URL)
        except Exception as e:
            self.logger.debug(f"Walmart init call failed (continuing): {e}")

        raw_by_id: dict = {}
        sem = asyncio.Semaphore(self.CONCURRENCY)
        errors: List[str] = []

        async def sweep(keyword: str):
            for page in range(self.PAGES_PER_KEYWORD):
                if loop.time() > deadline or len(raw_by_id) >= self.MAX_JOBS:
                    return
                async with sem:
                    if loop.time() > deadline:
                        return
                    try:
                        data = await self.fetch_json(
                            self.API_URL, method="POST", json_data=self._search_body(keyword, page)
                        )
                        jobs = self.extract_jobs(data)
                    except Exception as e:
                        errors.append(f"{keyword}/{page}: {e}")
                        return
                new = 0
                for j in jobs:
                    jid = j.get("job_id")
                    if jid and jid not in raw_by_id:
                        raw_by_id[jid] = j
                        new += 1
                if len(jobs) < 10 or new == 0:
                    return

        await asyncio.gather(*(sweep(k) for k in self.KEYWORDS))
        if not raw_by_id and errors:
            raise UnexpectedResponseError(f"all Walmart searches failed: {errors[0]}")
        jobs = self.parse_all(list(raw_by_id.values())[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs))

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            job_id = raw.get("job_id")
            title = self.clean_text(raw.get("jobPostingTitle") or raw.get("title"))
            if not job_id or not title:
                return None
            city = (raw.get("city") or "").title()
            loc = ", ".join(p for p in (city, raw.get("state"), raw.get("country")) if p)
            extra = raw.get("additionalLocationCities") or []
            if extra:
                loc = "; ".join([loc] + [str(c) for c in extra if c])
            posted = None
            ts = raw.get("jobPostingStartDate")
            if isinstance(ts, (int, float)) and ts > 0:
                posted = datetime.utcfromtimestamp(ts / 1000)
            salary_min = salary_max = None
            freq = (raw.get("payFrequency") or "").lower()
            if freq and "hour" not in freq:
                try:
                    salary_min = int(float(raw["minPay"])) if raw.get("minPay") else None
                    salary_max = int(float(raw["maxPay"])) if raw.get("maxPay") else None
                except (TypeError, ValueError):
                    pass
            categories = raw.get("categories") or []
            emp = raw.get("employmentTypes") or []
            return ScrapedJob(
                title=title,
                location=loc,
                job_url=self.JOB_URL.format(job_id=job_id),
                external_job_id=job_id,
                department=categories[0] if categories else None,
                posted_date=posted,
                salary_min=salary_min,
                salary_max=salary_max,
                employment_type=emp[0] if emp else None,
            )
        except Exception as e:
            self.logger.error(f"Error parsing Walmart job: {e}")
            return None
