"""
JobDiva candidate portals (www1/www2.jobdiva.com/portal/?a=<key>), mostly IT
staffing firms.

The portal is a single-page app; anonymous visitors get a session token from
GET ws.jobdiva.com/candPortal/rest/auth/a (the firm's public key in header
"a", plus the portal's own anonymous credential from its JS bundle) and list
jobs with POST .../job/searchjobsportal (form body, from/to paging). No
candidate account is involved. Verified 2026-10-05.

A board is "<host>.<key>": host www1 or www2 (the portal shard the firm's
site links to), key the portal's "a" parameter.
"""

import re
from datetime import datetime, timezone
from typing import List, Optional

from scrapers.base import ScrapedJob, ScrapeResult

JOBDIVA_WS = "https://ws.jobdiva.com/candPortal/rest"
# The candidate portal's anonymous credential, as its own JS bundle sends it.
JOBDIVA_PORTAL_AUTH = "Basic YXhlbG9uOmF4ZWxvbg=="
_HOSTS = ("www1", "www2")
_KEY = re.compile(r"[A-Za-z0-9]{20,120}")


def jobdiva_parts(board: str) -> Optional[tuple[str, str]]:
    """'www2.<key>' -> ('www2', key), or None when malformed."""
    host, _, key = (board or "").partition(".")
    if host not in _HOSTS or not _KEY.fullmatch(key):
        return None
    return host, key


def jobdiva_portal_url(board: str) -> Optional[str]:
    parts = jobdiva_parts(board)
    return f"https://{parts[0]}.jobdiva.com/portal/?a={parts[1]}" if parts else None


def jobdiva_search_form(start: int, end: int) -> dict:
    """The search the portal itself posts (all jobs, no filters)."""
    return {
        "city": "", "country": "", "from": str(start), "jobCategories": "", "jobDivisions": "",
        "jobTypes": "", "keywords": "", "miles": "", "onsiteFlex": "", "portalID": "1",
        "qualifications": "", "states": "", "to": str(end), "unit": "mi", "zipcode": "",
    }


class JobDivaMixin:
    PAGE_SIZE = 100
    MAX_JOBS = 2000

    async def _jobdiva_json(self, method: str, url: str, **kwargs):
        return await self._request(method, url, lambda r: r.json(content_type=None), **kwargs)

    async def scrape(self) -> ScrapeResult:
        parts = jobdiva_parts(self.BOARD)
        if not parts:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message=f"Bad JobDiva board {self.BOARD!r}")
        self._jobdiva = parts
        host, key = parts
        auth = await self._jobdiva_json(
            "GET", f"{JOBDIVA_WS}/auth/a",
            headers={"a": key, "compid": "-1", "portalid": "1", "Authorization": JOBDIVA_PORTAL_AUTH},
        )
        token = (auth or {}).get("token") if isinstance(auth, dict) else None
        if not token:
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message="JobDiva gave no portal token")
        headers = {"a": key, "compid": "-1", "portalid": str(auth.get("portalID") or 1), "token": token}

        raw: List[dict] = []
        total = 0
        start = 1
        while len(raw) < self.MAX_JOBS:
            data = await self._jobdiva_json(
                "POST", f"{JOBDIVA_WS}/job/searchjobsportal",
                data=jobdiva_search_form(start, start + self.PAGE_SIZE - 1), headers=headers,
            )
            rows = self.expect_list(data, "data")
            raw.extend(rows)
            total = int(data.get("total") or 0)
            if not rows or len(raw) >= total:
                break
            start += self.PAGE_SIZE
        jobs = self.parse_all(raw)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), error_message=None,
                            complete=len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            host, key = getattr(self, "_jobdiva", None) or jobdiva_parts(self.BOARD)
            job_id = str(raw.get("id") or "")
            if not job_id or not raw.get("title"):
                return None
            posted_ms = raw.get("postDate")
            posted = (datetime.fromtimestamp(posted_ms / 1000, tz=timezone.utc).replace(tzinfo=None)
                      if posted_ms else None)
            emp = raw.get("positionType") or ("Direct Hire" if str(raw.get("directPlacement")) == "1" else None)
            return ScrapedJob(
                title=raw.get("title", ""),
                location=raw.get("location") or "",
                job_url=f"https://{host}.jobdiva.com/portal/?a={key}#/jobs/{job_id}",
                external_job_id=job_id,
                job_description=raw.get("jobDescription") or "",
                posted_date=posted,
                employment_type_raw=emp,
                extra={"ref_no": raw.get("refNo"), "pay_rate": raw.get("payRate")},
            )
        except Exception:
            return None
