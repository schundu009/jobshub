"""
iCIMS career-portal scrapers (pure HTTP, no Playwright).

iCIMS portals ({tenant}.icims.com) render search results server-side when the
iframe variant is requested: GET /jobs/search?ss=1&in_iframe=1&pr={page}
(pr is 0-based). Each result is a `.iCIMS_JobsTable .row` containing an
`a.iCIMS_Anchor` link (/jobs/{id}/{slug}/job), a location header and an
`iCIMS_JobHeaderGroup` <dl> of extra fields (Requisition ID, Category, ...).
The page count is announced in the pager as "Page 1 of N".
"""

import asyncio
import re
from typing import List, Optional
from urllib.parse import urlsplit, urlunsplit

from bs4 import BeautifulSoup

from scrapers.base import (
    HTTPScraper,
    ScrapedJob,
    ScraperConfig,
    ScraperType,
    ScrapeResult,
    UnexpectedResponseError,
)
from scrapers.registry import ScraperRegistry

_JOB_ID_RE = re.compile(r"/jobs/(\d+)/")
_PAGE_COUNT_RE = re.compile(r"Page\s+\d+\s+of\s+(\d+)", re.I)
# iCIMS location codes: "US-IL-Chicago", "US-TX-Austin", "CA-ON-Toronto", "US-Remote"
_ICIMS_LOC_RE = re.compile(r"^([A-Z]{2})-([A-Z]{2})-(.+)$")


def normalize_icims_location(raw: str) -> str:
    """'US-IL-Chicago | US-TX-Austin' -> 'Chicago, IL, US; Austin, TX, US'."""
    parts = []
    for piece in (raw or "").split("|"):
        piece = piece.strip()
        if not piece:
            continue
        m = _ICIMS_LOC_RE.match(piece)
        parts.append(f"{m.group(3)}, {m.group(2)}, {m.group(1)}" if m else piece)
    return "; ".join(parts)


class ICIMSMixin:
    """
    Subclasses set ICIMS_HOST (e.g. "career-schwab.icims.com").

    Optional: SEARCH_PARAMS (extra query args, e.g. {"searchCategory": "123"}),
    MAX_PAGES / MAX_JOBS / TIME_BUDGET_SECONDS.
    """

    ICIMS_HOST: str = ""
    SEARCH_PARAMS: dict = {}
    MAX_PAGES = 60
    MAX_JOBS = 3000
    # Celery kills HTTP scrape tasks at a 120s soft limit; stay well inside it.
    TIME_BUDGET_SECONDS = 75

    @property
    def icims_search_url(self) -> str:
        return f"https://{self.ICIMS_HOST}/jobs/search"

    async def scrape(self) -> ScrapeResult:
        loop = asyncio.get_event_loop()
        deadline = loop.time() + self.TIME_BUDGET_SECONDS
        raw_jobs: List[dict] = []
        seen = set()
        total_pages: Optional[int] = None
        page = 0
        pages_scraped = 0

        while page < self.MAX_PAGES:
            params = {"ss": "1", "in_iframe": "1", "pr": str(page), **self.SEARCH_PARAMS}
            html = await self.fetch_html(self.icims_search_url, params=params)
            soup = BeautifulSoup(html, "html.parser")
            if page == 0:
                if soup.select_one(".iCIMS_JobsTable") is None and "iCIMS_" not in html:
                    raise UnexpectedResponseError("no iCIMS job table in search page")
                total_pages = self.icims_page_count(soup)
            rows = self.parse_search_page(soup)
            pages_scraped += 1
            new_rows = [r for r in rows if r["id"] not in seen]
            if not new_rows:
                break
            for r in new_rows:
                seen.add(r["id"])
            raw_jobs.extend(new_rows)
            page += 1
            if total_pages is not None and page >= total_pages:
                break
            if len(raw_jobs) >= self.MAX_JOBS or loop.time() > deadline:
                self.logger.info(f"iCIMS: stopping at {len(raw_jobs)} jobs (cap/time budget)")
                break
            await asyncio.sleep(0.2)

        jobs = self.parse_all(raw_jobs[: self.MAX_JOBS])
        return ScrapeResult(
            success=True, jobs=jobs, jobs_found=len(jobs),
            pages_scraped=pages_scraped, total_pages=total_pages,
        )

    @staticmethod
    def icims_page_count(soup: BeautifulSoup) -> Optional[int]:
        pager = soup.select_one(".iCIMS_Paging")
        text = pager.get_text(" ", strip=True) if pager else soup.get_text(" ", strip=True)
        m = _PAGE_COUNT_RE.search(text) or re.search(r"of\s+(\d+)", text)
        return int(m.group(1)) if m else None

    @staticmethod
    def parse_search_page(soup: BeautifulSoup) -> List[dict]:
        """Turn each result row of a search page into a plain dict."""
        out = []
        for row in soup.select(".iCIMS_JobsTable .row"):
            anchor = row.select_one("a.iCIMS_Anchor[href]")
            if not anchor:
                continue
            href = anchor["href"]
            m = _JOB_ID_RE.search(href)
            if not m:
                continue
            h3 = anchor.select_one("h3")
            title = (h3.get_text(" ", strip=True) if h3 else "") or (
                anchor.get("title", "").split(" - ", 1)[-1]
            )
            location = ""
            left = row.select_one(".header.left")
            if left:
                spans = [s for s in left.find_all("span") if "sr-only" not in (s.get("class") or [])]
                location = " ".join(s.get_text(" ", strip=True) for s in spans).strip()
            fields = {}
            for tag in row.select(".iCIMS_JobHeaderTag"):
                dt, dd = tag.select_one("dt"), tag.select_one("dd")
                if dt and dd:
                    fields[dt.get_text(" ", strip=True)] = dd.get_text(" ", strip=True)
            right = row.select_one(".header.right")
            right_text = right.get_text(" ", strip=True) if right else ""
            out.append({
                "id": m.group(1),
                "title": title,
                "href": href,
                "location": location,
                "fields": fields,
                "header_right": right_text,
            })
        return out

    @staticmethod
    def public_job_url(href: str) -> str:
        """Drop the ?in_iframe=1 query so the link opens the full-page posting."""
        parts = urlsplit(href)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            title = self.clean_text(raw.get("title"))
            if not title:
                return None
            fields = raw.get("fields") or {}
            posted = None
            for key in ("Posted Date", "Date Posted", "Posting Date"):
                if fields.get(key):
                    posted = self.parse_date(fields[key])
                    break
            if posted is None and raw.get("header_right"):
                m = re.search(r"\d{1,2}/\d{1,2}/\d{4}", raw["header_right"])
                if m:
                    posted = self.parse_date(m.group(0))
            department = fields.get("Category") or fields.get("Department") or fields.get("Job Category")
            employment_type = fields.get("Position Type") or fields.get("Type")
            return ScrapedJob(
                title=title,
                location=normalize_icims_location(raw.get("location", "")),
                job_url=self.public_job_url(raw["href"]),
                external_job_id=raw["id"],
                department=department or None,
                employment_type=employment_type or None,
                posted_date=posted,
                raw_data=raw,
            )
        except Exception as e:
            self.logger.error(f"Error parsing iCIMS job: {e}")
            return None


@ScraperRegistry.register(category="enterprise")
class SchwabICIMSScraper(ICIMSMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="schwab",
        company_name="Charles Schwab",
        careers_url="https://www.schwabjobs.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=60,
    )
    ICIMS_HOST = "career-schwab.icims.com"


@ScraperRegistry.register(category="enterprise")
class TollBrothersICIMSScraper(ICIMSMixin, HTTPScraper):
    config = ScraperConfig(
        company_slug="tollbrothers",
        company_name="Toll Brothers",
        careers_url="https://www.tollcareercenter.com/",
        scraper_type=ScraperType.HTTP,
        rate_limit=30,
        max_pages=20,
    )
    ICIMS_HOST = "jobs-tollbrothers.icims.com"
