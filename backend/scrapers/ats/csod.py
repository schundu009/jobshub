"""
Cornerstone OnDemand (CSOD) career sites as job_boards rows (ats "csod").

Board: "<corp>/<career site id>", from the career site address
<corp>.csod.com/ux/ats/careersite/<id>/home?c=<corp>, e.g. "cornerstone/2".
The career site page carries csod.context: an anonymous visitor token
(user -101) and the regional API host ("endpoints.cloud"); the page then
POSTs <cloud>rec-job-search/external/jobs with that token, which returns
{"data": {"totalCount", "requisitions": [{requisitionId, displayJobTitle,
locations[{city, state, country}], externalDescription, postingEffectiveDate}]}}.
This reads the same, 100 per page. A posting opens at
<site>/home/requisition/<id>?c=<corp>.
"""
import json
import re
from datetime import datetime
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import join_place
from scrapers.base import ScrapedJob, ScrapeResult, UnexpectedResponseError

_CORP = re.compile(r"[a-z0-9][a-z0-9\-]{0,62}")
_CONTEXT = re.compile(r"csod\.context\s*=\s*(\{.*?\})\s*;", re.S)


def _parts(board: str):
    corp, _, site = (board or "").partition("/")
    return (corp, site) if _CORP.fullmatch(corp) and site.isdigit() else None


def _site_url(board: str) -> str:
    corp, site = _parts(board)
    return f"https://{corp}.csod.com/ux/ats/careersite/{site}/home?c={corp}"


def csod_context(html: str) -> dict:
    m = _CONTEXT.search(html or "")
    try:
        return json.loads(m.group(1)) if m else {}
    except ValueError:
        return {}


class CsodMixin:
    PAGE_SIZE = 100
    MAX_JOBS = 1500

    def _search_body(self, page: int, context: dict) -> dict:
        site = int(_parts(self.BOARD)[1])
        return {
            "careerSiteId": site, "careerSitePageId": site, "pageNumber": page, "pageSize": self.PAGE_SIZE,
            "cultureId": context.get("cultureID") or 1, "searchText": "",
            "cultureName": context.get("cultureName") or "en-US", "states": [], "countryCodes": [],
            "cities": [], "placeID": "", "radius": None, "postingsWithinDays": None,
            "customFieldCheckboxKeys": [], "customFieldDropdowns": [], "customFieldRadios": [],
        }

    async def scrape(self) -> ScrapeResult:
        context = csod_context(await self.fetch_html(_site_url(self.BOARD)))
        token = context.get("token")
        cloud = ((context.get("endpoints") or {}).get("cloud") or "").rstrip("/")
        if not token or not re.fullmatch(r"https://[a-z0-9\-]+\.api\.csod\.com", cloud):
            raise UnexpectedResponseError("CSOD career site gave no visitor token / API host")
        headers = {"Authorization": f"Bearer {token}"}
        raw, total, page = [], None, 1
        while len(raw) < self.MAX_JOBS:
            data = await self.fetch_json(f"{cloud}/rec-job-search/external/jobs", method="POST",
                                         json_data=self._search_body(page, context), headers=headers)
            body = (data or {}).get("data") if isinstance(data, dict) else None
            reqs = self.expect_list(body or {}, "requisitions")
            total = int(body.get("totalCount") or 0)
            raw.extend(reqs)
            if not reqs or len(raw) >= total:
                break
            page += 1
        self._csod = _parts(self.BOARD)
        jobs = self.parse_all(raw[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=page,
                            complete=total is not None and len(raw) >= total)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        req_id, title = raw.get("requisitionId"), (raw.get("displayJobTitle") or "").strip()
        if not req_id or not title:
            return None
        corp, site = _parts(self.BOARD)
        places = [join_place(l.get("city"), l.get("state"), l.get("country")) for l in raw.get("locations") or []]
        places = [p for p in dict.fromkeys(places) if p]
        posted = None
        try:
            posted = datetime.strptime(raw.get("postingEffectiveDate") or "", "%m/%d/%Y")
        except ValueError:
            posted = None
        return ScrapedJob(
            title=title,
            location="; ".join(places[:3]),
            job_url=f"https://{corp}.csod.com/ux/ats/careersite/{site}/home/requisition/{req_id}?c={corp}",
            external_job_id=str(req_id),
            job_description=(raw.get("externalDescription") or "").strip() or None,
            posted_date=posted,
        )


register(BoardType(
    name="csod",
    mixin=CsodMixin,
    valid=lambda board: _parts(board) is not None,
    start_url=_site_url,
    careers_url=_site_url,
))
