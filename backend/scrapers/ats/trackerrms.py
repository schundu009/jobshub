"""
Tracker RMS published job lists as job_boards rows (ats "tracker-rms").

Board: "<portal host>/<database>|<job page base>", e.g.
"evoportalus.tracker-rms.com/GoldenTechnology|goldenitinc.com/careers/job/".
The employer's careers page loads GET <portal>/<database>/jobs with
fields=..., sorts, start, limit and joblinkuri=<its own job page>; Tracker
answers an HTML list (#trackerpublishlist, one <ul> per job of
li.publish_<field>). The job page base is where each posting opens
(<base>?jobcode=<n>); without one, postings link to Tracker's own apply page.
"""
import re
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import HOST, host_and_path, join_place, remote_from
from scrapers.base import ScrapedJob, ScrapeResult

FIELDS = "title,location,city,state,worktype,publishdate,reference,description,salaryfrom,salaryto,salaryper,joblink"
_DB = re.compile(r"[A-Za-z0-9_\-]{1,60}")


def _parts(board: str):
    portal, _, page = (board or "").partition("|")
    host, _, db = portal.partition("/")
    if not HOST.fullmatch(host.lower()) or not host.lower().endswith("tracker-rms.com") or not _DB.fullmatch(db):
        return None
    if page and not host_and_path(page.rstrip("/"), 0, 4):
        return None
    return host.lower(), db, (f"https://{page.rstrip('/')}/" if page else None)


def tracker_rows(html: str) -> list:
    soup = BeautifulSoup(html or "", "html.parser")
    rows = []
    root = soup.select_one("#trackerpublishlist")
    for job in root.select(":scope > ul > li") if root else []:
        row = {}
        for li in job.select("li[class^=publish_]"):
            name = (li.get("class") or [""])[0].replace("publish_", "")
            if name == "description":
                row[name] = li.decode_contents()
            elif name == "joblink":
                a = li.find("a")
                row[name] = a.get("href") if a else ""
                row["joblink_text"] = li.get_text(" ", strip=True)
            else:
                row[name] = li.get_text(" ", strip=True)
        rows.append(row)
    return rows


class TrackerRMSMixin:
    LIMIT = 500

    async def scrape(self) -> ScrapeResult:
        host, db, page = _parts(self.BOARD)
        params = {"fields": FIELDS, "filters": "", "sorts": "publishstartdate DESC", "start": "0",
                  "limit": str(self.LIMIT), "inject": "true"}
        if page:
            params["joblinkuri"] = page
        rows = tracker_rows(await self.fetch_html(self.API_URL, params=params))
        jobs = self.parse_all(rows)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=len(rows) < self.LIMIT)

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        title = (raw.get("title") or "").strip()
        m = re.search(r"(\d+)", raw.get("reference") or raw.get("joblink_text") or "")
        if not title or not m:
            return None
        code = m.group(1)
        host, db, page = _parts(self.BOARD)
        link = raw.get("joblink") or ""
        if not link.startswith("http"):
            link = f"{page}?jobcode={code}" if page else f"https://{host}/{db}/apply?jobcode={code}"
        posted = None
        try:
            posted = datetime.strptime(raw.get("publishdate") or "", "%d %b %Y")
        except ValueError:
            posted = None

        def money(key):
            try:
                return float(re.sub(r"[^\d.]", "", raw.get(key) or "")) or None
            except ValueError:
                return None
        per = (raw.get("salaryper") or "").lower()
        period = next((p for p in ("hour", "day", "week", "month", "year") if p in per), None)
        location = raw.get("location") or join_place(raw.get("city"), raw.get("state"))
        return ScrapedJob(
            title=title,
            location=location,
            job_url=link,
            external_job_id=code,
            job_description=(raw.get("description") or "").strip() or None,
            posted_date=posted,
            remote_type=remote_from(location),
            employment_type_raw=raw.get("worktype") or None,
            pay_rate_min=money("salaryfrom"), pay_rate_max=money("salaryto"), pay_period=period,
        )


register(BoardType(
    name="tracker-rms",
    mixin=TrackerRMSMixin,
    valid=lambda board: _parts(board) is not None,
    start_url=lambda board: "https://{0}/{1}/jobs".format(*_parts(board)),
    careers_url=lambda board: _parts(board)[2] or "https://{0}/{1}/jobs".format(*_parts(board)),
))
