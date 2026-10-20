"""
Volcanic recruitment sites (UK/US agency sites on Volcanic: Phaidon
International, Vallum Associates, ...).

Volcanic sites keep their JSON API under /api/ and their result pages under
/jobs?page=N, and their robots.txt disallows both (/api/* and /*?*). What
robots.txt does allow is the first results page (/jobs), the job sitemap
(/job/sitemap.xml, every live posting) and each posting's page (/job/<slug>-<id>),
which carries a schema.org JobPosting. So the scraper reads the cards on
/jobs, then the postings in the sitemap that page 1 did not show, from their
own pages. It stops at the first sign of the site's bot check (a challenge or
403) instead of retrying: some Volcanic sites sit behind AWS WAF.

A board is the site's host (vallumassociates.com).
"""

import asyncio
import re
from typing import Optional
from urllib.parse import urljoin, urlparse

import aiohttp
from bs4 import BeautifulSoup

from contracts.scrapers._base import parse_iso, parse_pay_text, simple_employment_type
from scrapers.ats import BoardType, register
from scrapers.ats._jobtext import (
    clean, jsonld_employment, jsonld_location, jsonld_pay, jsonld_postings, robots_allows,
)
from scrapers.base import ScrapedJob, ScrapeResult

_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
_JOB_PATH = re.compile(r"^/job/([a-z0-9\-]+-(\d+))/?$")
_LOC = re.compile(r"<loc>\s*([^<]+?)\s*</loc>")
_POSTED_AGO = re.compile(r"(\d+)\s+(day|week|month|hour)s?\s+ago", re.I)


def jobs_url(board: str) -> str:
    return f"https://{board}/jobs"


class BotCheck(Exception):
    """The site answered with its bot check (AWS WAF challenge, CAPTCHA) instead of the page."""


async def _read_page(response):
    if response.status == 202 or response.headers.get("x-amzn-waf-action"):
        raise BotCheck(f"{response.url.host} answered {response.status} "
                       f"(waf action {response.headers.get('x-amzn-waf-action') or 'unknown'})")
    text = await response.text()
    if not text.strip():
        raise BotCheck(f"{response.url.host} answered an empty page")
    return text


class VolcanicMixin:
    MAX_DETAILS = 60
    TIME_BUDGET_SECONDS = 50
    DETAIL_DELAY_SECONDS = 1.5  # posting pages slowly: these sites rate-check visitors

    async def _page(self, url: str) -> str:
        return await self._request("GET", url, _read_page)

    async def scrape(self) -> ScrapeResult:
        start = jobs_url(self.BOARD)
        if not await robots_allows(start):
            return ScrapeResult(success=False, error_message=f"robots.txt disallows {start}")
        try:
            first = await self._page(start)
        except BotCheck as e:
            # Never try to get past it; the next scheduled run tries again.
            return ScrapeResult(success=False, error_message=f"bot check, not scraped: {e}")
        cards = {c["id"]: c for c in self.result_cards(first, start)}
        if not cards:
            return ScrapeResult(success=False, error_message=f"no job cards on {start}")
        complete = True
        sitemap_url = f"https://{self.BOARD}/job/sitemap.xml"
        listed = []
        if await robots_allows(sitemap_url):
            try:
                listed = [u for u in _LOC.findall(await self._page(sitemap_url)) if _JOB_PATH.match(urlparse(u).path)]
            except (aiohttp.ClientError, BotCheck) as e:
                self.logger.info(f"job sitemap unavailable: {e}")
                complete = False
        else:
            complete = False
        deadline = asyncio.get_event_loop().time() + self.TIME_BUDGET_SECONDS
        missing = [u for u in listed if _JOB_PATH.match(urlparse(u).path).group(2) not in cards]
        for n, url in enumerate(missing):
            if n >= self.MAX_DETAILS or asyncio.get_event_loop().time() > deadline:
                complete = False
                break
            if not await robots_allows(url):
                continue
            await asyncio.sleep(self.DETAIL_DELAY_SECONDS)
            try:
                page = await self._page(url)
            except BotCheck as e:
                self.logger.info(f"{e}; leaving the remaining postings for the next run")
                complete = False
                break
            except aiohttp.ClientResponseError as e:
                if e.status in (403, 405, 429):
                    self.logger.info(f"{self.BOARD} answered {e.status}; leaving the remaining postings for the next run")
                    complete = False
                    break
                continue
            postings = jsonld_postings(page)
            if not postings:
                if "challenge" in page[:5000].lower() or "captcha" in page[:5000].lower():
                    complete = False
                    break
                continue
            job_id = _JOB_PATH.match(urlparse(url).path).group(2)
            cards[job_id] = {"id": job_id, "url": url, "ld": postings[0]}
        jobs = self.parse_all(list(cards.values()))
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=complete and bool(listed))

    @staticmethod
    def result_cards(page: str, base: str) -> list[dict]:
        soup = BeautifulSoup(page or "", "html.parser")
        out = []
        for item in soup.select("li.job-result-item"):
            link = item.select_one(".job-title a[href]") or item.find("a", href=True)
            if not link:
                continue
            url = urljoin(base, link["href"])
            m = _JOB_PATH.match(urlparse(url).path)
            if not m:
                continue

            def text(selector):
                node = item.select_one(selector)
                return clean(node.get_text(" ")) if node else ""
            out.append({"id": m.group(2), "url": url, "title": clean(link.get_text(" ")),
                        "location": text(".results-job-location"), "salary": text(".results-salary"),
                        "type": text(".results-job-type"), "posted": text(".results-posted-at"),
                        "summary": text(".job-description")})
        return out

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        ld = raw.get("ld") or {}
        title = raw.get("title") or clean(ld.get("title"))
        if not title or not raw.get("url"):
            return None
        location = raw.get("location") or (jsonld_location(ld) if ld else "")
        emp = raw.get("type") or (jsonld_employment(ld) if ld else None)
        if ld:
            lo, hi, period = jsonld_pay(ld)
        else:
            lo, hi, period = parse_pay_text(raw.get("salary"))
        posted = parse_iso(ld.get("datePosted")) if ld else None
        if not posted and raw.get("posted"):
            from datetime import datetime, timedelta
            m = _POSTED_AGO.search(raw["posted"])
            if m:
                days = {"hour": 0, "day": 1, "week": 7, "month": 30}[m.group(2).lower()] * int(m.group(1))
                posted = (datetime.utcnow() - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
        return ScrapedJob(
            title=title,
            location=location,
            job_url=raw["url"],
            external_job_id=raw["id"],
            job_description=self.clean_html(ld.get("description")) if ld.get("description") else raw.get("summary") or None,
            posted_date=posted,
            employment_type=simple_employment_type(emp),
            employment_type_raw=emp or None,
            pay_rate_min=lo,
            pay_rate_max=hi,
            pay_period=period,
            salary_min=int(lo) if period == "year" and lo else None,
            salary_max=int(hi) if period == "year" and hi else None,
            extra={"salary_text": raw["salary"]} if raw.get("salary") else {},
        )


register(BoardType(
    name="volcanic",
    mixin=VolcanicMixin,
    valid=lambda board: bool(_HOST.fullmatch(board or "")),
    start_url=jobs_url,
    careers_url=jobs_url,
))
