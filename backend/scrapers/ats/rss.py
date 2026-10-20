"""
A career site's own RSS / Atom job feed (WP Job Manager's ?feed=job_feed,
WP JobSearch's feed, a job post type's /feed/, and similar feeds job sites
publish for aggregators).

Items give the title, link and date; the location, type and pay come from
the feed's job fields when it has them (job_listing:location, <location>,
<city>/<state>, <job_type>, <salary>, ...), else from "Location:" style lines
in the item's description.

A board is the feed URL without the scheme, e.g.
"careers.cblsolutions.com/?feed=job_feed".
"""

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Optional

import aiohttp

from contracts.scrapers._base import join_location, parse_iso, parse_pay_text, simple_employment_type
from scrapers.ats import BoardType, register
from scrapers.ats._jobtext import LOCATION_LABELS, TYPE_LABELS, clean, html_text, label_value, pay_from_text
from scrapers.base import ScrapedJob, ScrapeResult, UnexpectedResponseError

_BOARD = re.compile(r"(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(?:/[^\s]*)?")
_ATOM = "{http://www.w3.org/2005/Atom}"


def feed_url(board: str) -> str:
    return f"https://{board}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _fields(item) -> dict:
    """Every child element as local-name -> text (first one wins; Atom link -> href)."""
    out = {}
    for child in item:
        name = _local(child.tag)
        value = child.get("href") if name == "link" and child.get("href") else (child.text or "")
        if name not in out or not out[name]:
            out[name] = value.strip()
    return out


def _date(value: str):
    if not value:
        return None
    try:
        return parsedate_to_datetime(value).replace(tzinfo=None)
    except (TypeError, ValueError, IndexError):
        return parse_iso(value)


class RssFeedMixin:
    MAX_JOBS = 1500
    FEED_TIMEOUT_SECONDS = 50

    async def scrape(self) -> ScrapeResult:
        # Some sites build the feed slowly (30 s+); wait longer than for an API call.
        body = await self._request("GET", feed_url(self.BOARD), lambda r: r.text(),
                                   timeout=aiohttp.ClientTimeout(total=self.FEED_TIMEOUT_SECONDS))
        try:
            root = ET.fromstring(body.lstrip("﻿ \r\n\t").encode("utf-8"))
        except ET.ParseError as e:
            raise UnexpectedResponseError(f"feed is not XML ({e}): {body[:80]!r}")
        channel = root.find("channel")
        items = channel.findall("item") if channel is not None else root.findall(f"{_ATOM}entry")
        jobs = self.parse_all([_fields(i) for i in items[: self.MAX_JOBS]])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=len(items) <= self.MAX_JOBS)

    def parse_job(self, f: dict) -> Optional[ScrapedJob]:
        title = clean(f.get("title"))
        link = f.get("link") or (f.get("guid") if str(f.get("guid", "")).startswith("http") else "")
        if not title or not link:
            return None
        description = f.get("encoded") or f.get("description") or f.get("content") or f.get("summary") or f.get("excerpt") or ""
        text = html_text(description)
        location = (clean(f.get("location") or f.get("joblocation") or f.get("job_location"))
                    or join_location(f.get("city"), f.get("state") or f.get("region"))
                    or label_value(text, LOCATION_LABELS) or clean(f.get("country")))
        emp = clean(f.get("job_type") or f.get("jobtype") or f.get("type") or f.get("employment_type")) or \
            label_value(text, TYPE_LABELS, max_len=40)
        lo, hi, period = parse_pay_text(f.get("salary") or f.get("payrate") or "")
        if not lo:
            lo, hi, period = pay_from_text(text)
        job_id = (f.get("recuiterjobnumber") or f.get("referencenumber") or f.get("id")
                  or (f.get("guid") if f.get("guid") and not str(f.get("guid")).startswith("http") else None)
                  or link.rstrip("/").rsplit("/", 1)[-1])
        return ScrapedJob(
            title=title,
            location=location or "",
            job_url=link,
            external_job_id=str(job_id),
            job_description=self.clean_html(description) if description else None,
            department=clean(f.get("job_category") or f.get("category") or f.get("sector")) or None,
            posted_date=_date(f.get("pubdate") or f.get("postdate") or f.get("published") or f.get("updated")),
            employment_type=simple_employment_type(emp),
            employment_type_raw=emp or None,
            pay_rate_min=lo,
            pay_rate_max=hi,
            pay_period=period,
            salary_min=int(lo) if period == "year" and lo else None,
            salary_max=int(hi) if period == "year" and hi else None,
            extra={"client": clean(f.get("company") or f.get("employer"))} if (f.get("company") or f.get("employer")) else {},
        )


register(BoardType(
    name="rss",
    mixin=RssFeedMixin,
    valid=lambda board: bool(_BOARD.fullmatch(board or "")) and not board.startswith(("http:", "https:")),
    start_url=feed_url,
))
