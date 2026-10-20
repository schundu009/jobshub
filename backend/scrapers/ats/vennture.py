"""
Vennture recruitment sites (UK agencies on the Venn / wearevennture
platform: Hamilton Barnes, Spectrum IT, Understanding Recruitment, ...).

The site's job-search page talks to one shared gateway. An anonymous visitor
gets a short-lived JobSearch session from

    GET https://gateway.wearevennture.co.uk/auth?session=null&user=null

and searches with it:

    POST https://gateway.wearevennture.co.uk/job-search?local=uk&organisation=
         {"queryString": null, "pageSize": 100, "nextPageToken": ...}
    -> {"jobs": [...], "totalCount": N, "nextPageToken": "..."}

The gateway picks the agency from the Origin the page sends, so a board is
the site's host (www.hamilton-barnes.com) and requests carry that site's
Origin and Referer, exactly as its own page does. Jobs' "url" is a path on
the same site (/candidates/job/<slug>/).
"""

import re
from typing import List, Optional

from contracts.scrapers._base import parse_iso, parse_pay_text, simple_employment_type, to_float, norm_period
from scrapers.ats import BoardType, register
from scrapers.base import ScrapedJob, ScrapeResult

GATEWAY = "https://gateway.wearevennture.co.uk"
_HOST = re.compile(r"(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")
_PERIODS = {"YEARLY": "year", "ANNUAL": "year", "HOURLY": "hour", "DAILY": "day", "WEEKLY": "week", "MONTHLY": "month"}


def search_url(board: str) -> str:
    # One gateway for every agency; the fragment keeps each board's URL distinct.
    return f"{GATEWAY}/job-search?local=uk&organisation=#{board}"


class VenntureMixin:
    PAGE_SIZE = 100
    MAX_JOBS = 1500

    def _site_headers(self) -> dict:
        origin = f"https://{self.BOARD}"
        return {"Origin": origin, "Referer": origin + "/"}

    async def scrape(self) -> ScrapeResult:
        session = await self.fetch_json(f"{GATEWAY}/auth?session=null&user=null", headers=self._site_headers())
        token = session.get("jwt") if isinstance(session, dict) else None
        if not token:
            return ScrapeResult(success=False, error_message="Vennture gateway gave no search session")
        headers = {**self._site_headers(), "Authorization": f"Bearer {token}"}
        raw: List[dict] = []
        total = 0
        page_token = None
        while len(raw) < self.MAX_JOBS:
            body = {"queryString": None, "enableSpellCheck": True, "userId": session.get("uid"),
                    "sessionId": session.get("sid"), "location": {"telecommute": 0, "address": None},
                    "pageSize": self.PAGE_SIZE}
            if page_token:
                body["nextPageToken"] = page_token
            data = await self.fetch_json(f"{GATEWAY}/job-search?local=uk&organisation=", method="POST",
                                         json_data=body, headers=headers)
            rows = self.expect_list(data, "jobs")
            raw.extend(rows)
            total = int(data.get("totalCount") or 0)
            page_token = data.get("nextPageToken")
            if not rows or not page_token or len(raw) >= total:
                break
        jobs = self.parse_all(raw)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        title = (raw.get("title") or "").strip()
        path = (raw.get("url") or "").strip()
        job_id = str(raw.get("id") or "")
        if not title or not path or not job_id:
            return None
        location = ((raw.get("location") or {}).get("address") or "").strip()
        if not location and raw.get("remoteWorking"):
            location = "Remote"
        # jobTypes mixes the type with the salary figure: ["Permanent", "40000\r\n"].
        types = [str(t).strip() for t in raw.get("jobTypes") or [] if t and not re.search(r"\d", str(t))]
        types = [t for i, t in enumerate(types) if t and t not in types[:i]]
        emp = ", ".join(types) or None
        salary_text = (raw.get("salaryText") or "").strip()
        period = _PERIODS.get(str((raw.get("customFields") or {}).get("salaryper") or "").upper())
        lo, hi = to_float(raw.get("salaryMinimum")), to_float(raw.get("salaryMaximum"))
        t_lo, t_hi, t_period = parse_pay_text(salary_text)
        if t_lo:
            lo, hi, period = t_lo, t_hi or hi or t_lo, period or t_period
        elif lo or hi:
            lo, hi = lo or hi, hi or lo
        if not period:
            period = norm_period(salary_text) or ("year" if (lo or 0) >= 10000 else None)
        if not period:
            lo = hi = None
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"https://{self.BOARD}{path if path.startswith('/') else '/' + path}",
            external_job_id=job_id,
            job_description=self.clean_html(raw.get("description")),
            posted_date=parse_iso(raw.get("postDate")),
            employment_type=simple_employment_type(emp),
            employment_type_raw=emp,
            remote_type="remote" if raw.get("remoteWorking") else None,
            pay_rate_min=lo,
            pay_rate_max=hi,
            pay_period=period if lo else None,
            salary_min=int(lo) if period == "year" and lo else None,
            salary_max=int(hi) if period == "year" and hi else None,
            extra={k: v for k, v in {"salary_text": salary_text or None, "reference": raw.get("reference"),
                                     "currency": raw.get("salaryCurrency")}.items() if v},
        )


register(BoardType(
    name="vennture",
    mixin=VenntureMixin,
    valid=lambda board: bool(_HOST.fullmatch(board or "")),
    start_url=search_url,
    careers_url=lambda board: f"https://{board}/",
))
