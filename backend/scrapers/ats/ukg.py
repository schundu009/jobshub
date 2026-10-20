"""
UKG Ready (Kronos Workforce Ready, *.saashr.com) career sites as job_boards
rows (ats "ukg").

Board: "<host>/<company>", from the career site address
https://<host>/ta/<company>.careers, e.g. "secure5.saashr.com/PayServ221004".
The career page lists jobs from
GET <host>/ta/rest/ui/recruitment/companies/|<company>/job-requisitions?offset=1&size=N&sort=desc&lang=en-US
-> {"job_requisitions": [{id, job_title, location{city, state, country},
employee_type{name}, job_description, is_remote_job, base_pay_from/to,
base_pay_frequency}], "_paging": {offset, size, total}}. A job opens at
<host>/ta/<company>.careers?ShowJob=<id>.
"""
import re
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import join_place
from scrapers.base import ScrapedJob, ScrapeResult

_HOST = re.compile(r"[a-z0-9\-]+\.saashr\.com")
_COMPANY = re.compile(r"[A-Za-z0-9_\-]{1,60}")


def _parts(board: str):
    host, _, company = (board or "").partition("/")
    return (host.lower(), company) if _HOST.fullmatch(host.lower()) and _COMPANY.fullmatch(company) else None


class UKGReadyMixin:
    PAGE_SIZE = 200
    MAX_PAGES = 10

    async def scrape(self) -> ScrapeResult:
        raw, seen, total, offset = [], set(), None, 1
        for _ in range(self.MAX_PAGES):
            data = await self.fetch_json(self.API_URL, params={
                "offset": str(offset), "size": str(self.PAGE_SIZE), "sort": "desc", "lang": "en-US"})
            rows = self.expect_list(data, "job_requisitions")
            total = int(((data.get("_paging") or {}).get("total")) or 0)
            fresh = [r for r in rows if r.get("id") not in seen]
            seen.update(r.get("id") for r in fresh)
            raw.extend(fresh)
            if not fresh or len(raw) >= total:
                break
            offset += 1
        jobs = self.parse_all(raw)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs),
                            complete=total is not None and len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job_id, title = raw.get("id"), (raw.get("job_title") or "").strip()
        if not job_id or not title:
            return None
        host, company = _parts(self.BOARD)
        loc = raw.get("location") or {}
        if raw.get("is_remote_job"):
            location = raw.get("selected_loc_value_for_cp_display") or "Remote"
        else:
            location = join_place(loc.get("city"), loc.get("state"), loc.get("country"))

        def pay(key):
            try:
                return float(raw.get(key)) or None
            except (TypeError, ValueError):
                return None
        freq = str(raw.get("base_pay_frequency") or "").lower()
        period = next((p for p in ("hour", "day", "week", "month", "year") if p in freq), None)
        return ScrapedJob(
            title=title,
            location=location,
            job_url=f"https://{host}/ta/{company}.careers?ShowJob={job_id}",
            external_job_id=str(job_id),
            job_description=raw.get("job_description") or None,
            remote_type="remote" if raw.get("is_remote_job") else None,
            employment_type_raw=(raw.get("employee_type") or {}).get("name") or None,
            pay_rate_min=pay("base_pay_from"), pay_rate_max=pay("base_pay_to"), pay_period=period,
        )


register(BoardType(
    name="ukg",
    mixin=UKGReadyMixin,
    valid=lambda board: _parts(board) is not None,
    start_url=lambda board: "https://{0}/ta/rest/ui/recruitment/companies/%7C{1}/job-requisitions".format(*_parts(board)),
    careers_url=lambda board: "https://{0}/ta/{1}.careers?CareersSearch".format(*_parts(board)),
))
