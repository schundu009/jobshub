"""
Ceipal career portals (jobsapi.ceipal.com widget), used by many IT staffing firms.

The firm's careers page loads widget.js, which frames Ceipal's portal; the
portal lists jobs from careerapi.ceipal.com/<api key>/CareerPortalJobPostings/
?page=N, 20 a page. That API answers "Bot access is not allowed" to scripted
clients and to headless browsers, so the board is read the way a visitor reads
it: the firm's own careers page in a real (headed) Chromium, on the worker's
virtual display, paging with the widget's own page links. No stealth or
fingerprint changes; the browser is plain Playwright Chromium. Verified
2026-10-20 (cyberThink 142 jobs, VDart 843).

A board is the careers page that hosts the widget, without the scheme:
"cyberthink.com/careers-at-cyberthink/search-job/". A job opens on that page
with ?job_id=<id>, which the widget reads.
"""

import asyncio
import os
import platform
import re
import shutil
import subprocess
import time
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from scrapers.ats import BoardType, register
from scrapers.base import ScrapedJob, ScrapeResult

_PAGE = re.compile(
    r"(?=.{4,240}$)(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}(?:/[A-Za-z0-9._~%!$&'()*+,;=:@\-/?]*)?"
)
_POSTINGS = "CareerPortalJobPostings"


def valid_board(board: str) -> bool:
    return bool(board) and "://" not in board and bool(_PAGE.fullmatch(board))


def page_url(board: str) -> str:
    return f"https://{board}"


def job_url(board: str, job_id: str) -> str:
    parts = urlsplit(page_url(board))
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "job_id"] + [("job_id", job_id)]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))


def location_of(raw: dict) -> str:
    many = (raw.get("multpile_job_location") or "").strip()  # Ceipal's spelling
    if many:
        # "(Middletown, PA, 17057)" or "(Austin, TX, 78701), (Dallas, TX)"
        places = [re.sub(r",\s*\d{5}(?:-\d{4})?$", "", p.strip(" ()")) for p in many.split("),")]
        return "; ".join(p for p in places if p)
    return ", ".join(p for p in (raw.get("city"), raw.get("state"), raw.get("country")) if p)


def has_display() -> bool:
    """A headed browser needs a display: X (DISPLAY, Xvfb on the worker) or a desktop OS."""
    return bool(os.environ.get("DISPLAY")) or platform.system() in ("Darwin", "Windows")


_XVFB_DISPLAY = ":99"


def ensure_display() -> bool:
    """
    Start Xvfb when there is no display and it is installed. The worker's
    Railway start command runs celery directly (not worker_entrypoint.sh), so
    the scraper cannot rely on the entrypoint having started it. Forked pool
    processes share one server: whoever finds its socket just uses it.
    """
    if has_display():
        return True
    if not shutil.which("Xvfb"):
        return False
    sock = f"/tmp/.X11-unix/X{_XVFB_DISPLAY[1:]}"
    if not os.path.exists(sock):
        subprocess.Popen(["Xvfb", _XVFB_DISPLAY, "-screen", "0", "1366x900x24", "-nolisten", "tcp"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        for _ in range(50):
            if os.path.exists(sock):
                break
            time.sleep(0.1)
    if not os.path.exists(sock):
        return False
    os.environ["DISPLAY"] = _XVFB_DISPLAY
    return True


class CeipalMixin:
    OWN_BROWSER = True            # launches its own headed Chromium, not the shared headless pool
    MAX_JOBS = 1500
    TIME_BUDGET_SECONDS = 240     # the browser queue allows 5 minutes
    FIRST_PAGE_TIMEOUT = 45
    PAGE_TIMEOUT = 30

    async def scrape(self) -> ScrapeResult:
        board = self.BOARD
        if not valid_board(board):
            return ScrapeResult(success=False, jobs=[], jobs_found=0, error_message=f"Bad Ceipal board {board!r}")
        if not ensure_display():
            return ScrapeResult(success=False, jobs=[], jobs_found=0,
                                error_message="Ceipal needs a headed browser and there is no DISPLAY (Xvfb missing)")
        try:
            pages, total_pages = await self._read_pages(page_url(board))
        except asyncio.TimeoutError:
            return ScrapeResult(success=False, jobs=[], jobs_found=0,
                                error_message="The Ceipal widget sent no job list (page moved or widget refused)")
        seen: set = set()
        raw = []
        for n in sorted(pages):
            for row in pages[n]:
                if row.get("id") not in seen:  # a firm's regional widgets can share postings
                    seen.add(row.get("id"))
                    raw.append(row)
        raw = raw[: self.MAX_JOBS]
        jobs = self.parse_all(raw)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), error_message=None,
                            complete=len(pages) >= total_pages)

    async def _read_pages(self, url: str) -> tuple[dict, int]:
        """
        {(widget key, page): rows} for every Ceipal widget on the page (a firm
        may embed one per region), and the number of pages they hold in all.
        """
        from playwright.async_api import async_playwright

        started = time.monotonic()
        responses: asyncio.Queue = asyncio.Queue()
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=False)
            try:
                page = await browser.new_page()
                page.on("response", lambda r: responses.put_nowait(r) if _POSTINGS in r.url else None)
                await page.goto(url, wait_until="domcontentloaded", timeout=60000)
                widgets: dict[str, dict] = {}  # key -> {frame, pages}
                await self._take(widgets, await self._next_listing(responses, self.FIRST_PAGE_TIMEOUT))
                # Other widgets on the page load their first page around the same time.
                while True:
                    try:
                        await self._take(widgets, await self._next_listing(responses, 6))
                    except asyncio.TimeoutError:
                        break
                for key, w in widgets.items():
                    while (len(w["pages"]) < w["num_pages"]
                           and self._count(widgets) < self.MAX_JOBS
                           and time.monotonic() - started < self.TIME_BUDGET_SECONDS):
                        want = max(w["pages"]) + 1
                        try:
                            # The widget's own pager calls loadJobPostings(n).
                            await w["frame"].evaluate("n => loadJobPostings(n)", want)
                            before = len(w["pages"])
                            while len(w["pages"]) == before:
                                await self._take(widgets, await self._next_listing(responses, self.PAGE_TIMEOUT))
                        except Exception as e:
                            self.logger.info(f"Ceipal paging of widget {key[:8]} stopped at page {want}: {e}")
                            break
                pages = {(key, n): rows for key, w in widgets.items() for n, rows in w["pages"].items()}
                return pages, sum(w["num_pages"] for w in widgets.values())
            finally:
                await browser.close()

    @staticmethod
    async def _take(widgets: dict, resp) -> None:
        data = await resp.json()
        key = urlsplit(resp.url).path.strip("/").split("/")[0]
        w = widgets.setdefault(key, {"frame": resp.frame, "pages": {}, "num_pages": 1})
        w["num_pages"] = int(data.get("num_pages") or 1)
        w["pages"][int(data.get("page_number") or len(w["pages"]) + 1)] = data.get("results") or []

    @staticmethod
    def _count(widgets: dict) -> int:
        return sum(len(rows) for w in widgets.values() for rows in w["pages"].values())

    @staticmethod
    async def _next_listing(responses: asyncio.Queue, timeout: float):
        while True:
            resp = await asyncio.wait_for(responses.get(), timeout)
            if resp.status == 200:
                return resp

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            job_id = str(raw.get("id") or "")
            title = (raw.get("public_job_title") or raw.get("job_title") or "").strip()
            if not job_id or not title:
                return None
            location = location_of(raw)
            remote = "remote" if str(raw.get("remote_opportunities")) == "1" else None
            if remote and "remote" not in location.lower():
                location = f"{location} (Remote)" if location else "Remote"
            return ScrapedJob(
                title=title,
                location=location,
                job_url=job_url(self.BOARD, job_id),
                external_job_id=raw.get("job_code") or job_id,
                job_description=(raw.get("public_job_desc") or "").strip() or None,
                remote_type=remote,
                employment_type_raw=raw.get("job_type") or raw.get("employment_type") or None,
                extra={"tax_terms": raw["tax_terms"]} if raw.get("tax_terms") else {},
            )
        except Exception:
            return None


register(BoardType(
    name="ceipal",
    mixin=CeipalMixin,
    valid=valid_board,
    start_url=page_url,
    careers_url=page_url,
    browser=True,
))
