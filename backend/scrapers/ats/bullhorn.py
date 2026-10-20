"""
Bullhorn's public career-portal REST (OSCP: the open-source career portal a
staffing firm hosts on its own site reads it straight from the browser).

    GET https://public-restNN.bullhornstaffing.com/rest-services/<corpToken>/search/JobOrder
        ?query=(isOpen:1) AND (isDeleted:0)&fields=...&count=200&start=N&sort=-dateLastPublished

The swimlane NN and corpToken are in the portal's own app.json
(service.swimlane / service.corpToken). Only the jobs the firm publishes to
its portal come back; no login is involved.

A board is "public-restNN/<corpToken>@<job url prefix>": the prefix (no
scheme) is where the firm's portal shows one job, the job id appended:
  public-rest30/3vcpe1@cei.ai/jobs/#/jobs/        -> https://cei.ai/jobs/#/jobs/32932
  public-rest30/1XOC9@labur.com/career-portal/jobs/ -> https://labur.com/career-portal/jobs/9061
"""

import re
from typing import List, Optional
from urllib.parse import quote

from contracts.scrapers._base import join_location, norm_period, parse_iso, simple_employment_type, to_float
from scrapers.ats import BoardType, register
from scrapers.ats._jobtext import LOCATION_LABELS, html_text, label_value, pay_from_text
from scrapers.base import ScrapedJob, ScrapeResult

_BOARD = re.compile(
    r"(public-rest\d{1,3})/([A-Za-z0-9]{3,12})@((?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}[^\s@]*)"
)
QUERY = "(isOpen:1) AND (isDeleted:0)"
FIELDS = ("id,title,publishedCategory(id,name),address(city,state,zip,countryID),employmentType,"
          "dateLastPublished,dateAdded,publicDescription,salary,salaryUnit,payRate")
# Bullhorn country ids the portals use most (the rest leave the country off).
_COUNTRIES = {1: "United States", 2216: "Canada", 2359: "United Kingdom"}


def bullhorn_parts(board: str) -> Optional[tuple[str, str, str]]:
    """'public-rest30/3vcpe1@cei.ai/jobs/#/jobs/' -> ('public-rest30', '3vcpe1', 'cei.ai/jobs/#/jobs/')."""
    m = _BOARD.fullmatch((board or "").strip())
    return (m.group(1), m.group(2), m.group(3)) if m else None


def search_url(board: str, start: int = 0, count: int = 200) -> str:
    lane, token, _ = bullhorn_parts(board)
    return (f"https://{lane}.bullhornstaffing.com/rest-services/{token}/search/JobOrder"
            f"?query={quote(QUERY)}&fields={quote(FIELDS, safe=',()')}&count={count}&start={start}"
            f"&sort=-dateLastPublished")


def portal_url(board: str) -> Optional[str]:
    parts = bullhorn_parts(board)
    if not parts:
        return None
    prefix = parts[2]
    base = prefix.split("#", 1)[0]
    return f"https://{base}"


class BullhornMixin:
    PAGE_SIZE = 200
    MAX_JOBS = 1500

    async def scrape(self) -> ScrapeResult:
        raw: List[dict] = []
        total = 0
        start = 0
        while len(raw) < self.MAX_JOBS:
            data = await self.fetch_json(search_url(self.BOARD, start, self.PAGE_SIZE))
            rows = self.expect_list(data, "data")
            raw.extend(rows)
            total = int(data.get("total") or 0)
            if not rows or len(raw) >= total:
                break
            start += len(rows)
        jobs = self.parse_all(raw)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs),
                            complete=len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id = str(raw.get("id") or "")
        title = (raw.get("title") or "").strip()
        if not job_id or not title:
            return None
        address = raw.get("address") or {}
        country = (address.get("countryName") or _COUNTRIES.get(address.get("countryID")) or "").strip() or None
        city, state = address.get("city"), address.get("state")
        # "Syracuse, New York"; "Houston, United States" when the state is missing.
        location = join_location(city, state) if state else join_location(city, country)
        text = html_text(raw.get("publicDescription"))
        if not city:
            # Portals that only set the country often say where in the posting ("Location: London").
            location = label_value(text, LOCATION_LABELS) or location
        emp = (raw.get("employmentType") or "").strip() or None
        unit = str(raw.get("salaryUnit") or "")
        pay_rate = to_float(raw.get("payRate"))
        salary = to_float(raw.get("salary"))
        pay_min = pay_max = period = None
        salary_min = salary_max = None
        if pay_rate:
            pay_min = pay_max = pay_rate
            period = norm_period(unit) or "hour"
        elif salary:
            period = norm_period(unit) or ("year" if salary >= 1000 else None)
            if period:
                pay_min = pay_max = salary
            if period == "year":
                salary_min = salary_max = int(salary)
        if not pay_min:
            # Many firms leave payRate empty and state the rate in the posting ("Pay: $63.00/hour").
            pay_min, pay_max, period = pay_from_text(text)
        category = (raw.get("publishedCategory") or {}).get("name")
        _, _, prefix = bullhorn_parts(self.BOARD)
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"https://{prefix}{job_id}",
            external_job_id=job_id,
            job_description=self.clean_html(raw.get("publicDescription")),
            department=category,
            posted_date=parse_iso(raw.get("dateLastPublished") or raw.get("dateAdded")),
            salary_min=salary_min,
            salary_max=salary_max,
            employment_type=simple_employment_type(emp),
            employment_type_raw=emp,
            pay_rate_min=pay_min,
            pay_rate_max=pay_max,
            pay_period=period,
            extra={"zip": address.get("zip"), "country": country} if address.get("zip") or country else {},
        )


register(BoardType(
    name="bullhorn",
    mixin=BullhornMixin,
    valid=lambda board: bullhorn_parts(board) is not None,
    start_url=lambda board: search_url(board, 0),
    careers_url=portal_url,
))
