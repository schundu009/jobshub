"""
Haley Marketing job boards (jobs.<firm>.com, "HMS"/"HMG" boards many US
staffing firms run, often fed from Bullhorn).

Every board publishes its whole job list as RSS with Haley's job namespace
(city, state, country, jobtype, category, payrate, referencenumber):

    GET https://jobs.<firm>.com/rss/rss.smpl?ff=1&view=1

That feed is what the board itself links as its RSS; job links are the
board's own /jb/<title>/<id> pages. A board is the board's host name.
"""

import re
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from typing import Optional

from contracts.scrapers._base import join_location, parse_pay_text, simple_employment_type
from scrapers.ats import BoardType, register
from scrapers.ats._jobtext import TYPE_LABELS, html_text, label_value, pay_from_text
from scrapers.base import ScrapedJob, ScrapeResult

NS = {"job": "http://haleymarketing.com/rss/2.0/modules/job/"}
_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
# "Senior Supplier Enablement Specialist : 26-03185" -> the title, the board's reference.
_REF_SUFFIX = re.compile(r"\s*[:|#]\s*([A-Za-z]{0,4}-?\d[\w\-]*)\s*$")


def feed_url(board: str) -> str:
    return f"https://{board}/rss/rss.smpl?ff=1&view=1"


def _text(item, path: str) -> str:
    node = item.find(path, NS)
    return (node.text or "").strip() if node is not None and node.text else ""


class HaleyMixin:
    MAX_JOBS = 1500

    async def scrape(self) -> ScrapeResult:
        body = await self._request("GET", feed_url(self.BOARD), lambda r: r.text())
        items = self.feed_items(body)
        raw = items[: self.MAX_JOBS]
        jobs = self.parse_all(raw)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=len(items) <= self.MAX_JOBS)

    def feed_items(self, body: str) -> list:
        from scrapers.base import UnexpectedResponseError
        try:
            root = ET.fromstring(body.strip().encode("utf-8"))
        except ET.ParseError as e:
            raise UnexpectedResponseError(f"Haley feed is not XML ({e}): {body[:80]!r}")
        channel = root.find("channel")
        if channel is None:
            raise UnexpectedResponseError("Haley feed has no <channel>")
        return channel.findall("item")

    def parse_job(self, item) -> Optional[ScrapedJob]:
        title = _text(item, "title")
        link = _text(item, "link")
        if not title or not link:
            return None
        ref = None
        m = _REF_SUFFIX.search(title)
        if m:
            ref, title = m.group(1), title[: m.start()].strip()
        job_id = _text(item, "job:referencenumber") or link.rstrip("/").rsplit("/", 1)[-1]
        country = _text(item, "job:country")
        location = join_location(_text(item, "job:city"), _text(item, "job:state")) or country
        description = _text(item, "description")
        text = html_text(description)
        emp = _text(item, "job:jobtype") or label_value(text, TYPE_LABELS, max_len=40)
        pay_min, pay_max, period = parse_pay_text(_text(item, "job:payrate"))
        if not pay_min:
            pay_min, pay_max, period = pay_from_text(text)
        posted = None
        try:
            posted = parsedate_to_datetime(_text(item, "pubDate")).replace(tzinfo=None) if _text(item, "pubDate") else None
        except (TypeError, ValueError):
            posted = None
        return ScrapedJob(
            title=title,
            location=location,
            job_url=link,
            external_job_id=job_id,
            job_description=self.clean_html(description),
            department=_text(item, "job:category") or None,
            posted_date=posted,
            employment_type=simple_employment_type(emp),
            employment_type_raw=emp or None,
            pay_rate_min=pay_min,
            pay_rate_max=pay_max,
            pay_period=period,
            salary_min=int(pay_min) if period == "year" and pay_min else None,
            salary_max=int(pay_max) if period == "year" and pay_max else None,
            extra={k: v for k, v in {"ref_no": ref, "pay_rate": _text(item, "job:payrate") or None,
                                     "country": country or None}.items() if v},
        )


register(BoardType(
    name="haley",
    mixin=HaleyMixin,
    valid=lambda board: bool(_HOST.fullmatch(board or "")),
    start_url=feed_url,
    careers_url=lambda board: f"https://{board}/",
))
