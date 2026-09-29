#!/usr/bin/env python3
"""
Read-only health check for hard-coded ATS job boards.

Walks the ScraperRegistry, finds every HTTP scraper whose API URL points at a
public job-board API (Greenhouse, Ashby, Lever, SmartRecruiters, Workable),
issues ONE GET per board and reports HTTP status + job count.

Workday boards are only checked with --workday: their CXS API needs a
(read-only) search POST, sent with limit=1.

Usage (from backend/):
    python scripts/check_ats_boards.py            # table of all boards
    python scripts/check_ats_boards.py --bad      # only 404 / 0 jobs / errors
    python scripts/check_ats_boards.py --json     # machine-readable output
    python scripts/check_ats_boards.py --workday  # also check Workday boards
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Optional

import httpx

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from scrapers.registry import ScraperRegistry  # noqa: E402

CONCURRENCY = 4
TIMEOUT = 15.0
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; cariara-board-check/1.0)"}

# (ats, regex on the scraper's API URL, canonical GET url template, counter)
ATS_PATTERNS = [
    (
        "greenhouse",
        re.compile(r"boards-api\.greenhouse\.io/v1/boards/([^/?#]+)"),
        "https://boards-api.greenhouse.io/v1/boards/{slug}/jobs",
    ),
    (
        "ashby",
        re.compile(r"api\.ashbyhq\.com/posting-api/job-board/([^/?#]+)"),
        "https://api.ashbyhq.com/posting-api/job-board/{slug}?includeCompensation=false",
    ),
    (
        "lever",
        re.compile(r"api\.lever\.co/v0/postings/([^/?#]+)"),
        "https://api.lever.co/v0/postings/{slug}?mode=json",
    ),
    (
        "smartrecruiters",
        re.compile(r"api\.smartrecruiters\.com/v1/companies/([^/?#]+)"),
        "https://api.smartrecruiters.com/v1/companies/{slug}/postings?limit=1",
    ),
    (
        "workable",
        re.compile(r"apply\.workable\.com/api/v\d/(?:widget/)?accounts/([^/?#]+)"),
        "https://apply.workable.com/api/v1/widget/accounts/{slug}",
    ),
]


@dataclass
class BoardResult:
    company_slug: str
    scraper: str
    ats: str
    board: str
    url: str
    status: Optional[int] = None
    jobs: Optional[int] = None
    error: Optional[str] = None

    @property
    def ok(self) -> bool:
        return self.status == 200 and (self.jobs or 0) > 0


WORKDAY_RE = re.compile(r"https://([^/]+)/wday/cxs/([^/]+)/([^/]+)/jobs")


def count_jobs(ats: str, payload) -> int:
    if ats == "workday":
        return int(payload.get("total", 0) or 0)
    if ats == "lever":
        return len(payload) if isinstance(payload, list) else 0
    if ats == "smartrecruiters":
        return int(payload.get("totalFound", 0) or 0)
    return len(payload.get("jobs", []) or [])


def scraper_api_url(scraper_cls) -> Optional[str]:
    url = getattr(scraper_cls, "API_URL", None)
    if not url:
        url = getattr(scraper_cls.config, "api_url", None)
    return url if isinstance(url, str) else None


def board_for(scraper_cls, workday: bool = False) -> Optional[tuple[str, str, str]]:
    url = scraper_api_url(scraper_cls)
    if not url:
        return None
    if workday:
        m = WORKDAY_RE.search(url)
        if m:
            return "workday", f"{m.group(2)}/{m.group(3)}", m.group(0)
    for ats, pattern, template in ATS_PATTERNS:
        m = pattern.search(url)
        if m:
            slug = m.group(1)
            return ats, slug, template.format(slug=slug)
    return None


def collect_boards(workday: bool = False) -> list[BoardResult]:
    results = []
    for slug, cls in sorted(ScraperRegistry.get_all().items()):
        if cls.config.scraper_type.value != "http":
            continue
        found = board_for(cls, workday)
        if not found:
            continue
        ats, board, url = found
        results.append(BoardResult(slug, cls.__name__, ats, board, url))
    return results


async def check_one(client: httpx.AsyncClient, sem: asyncio.Semaphore, r: BoardResult) -> None:
    async with sem:
        try:
            if r.ats == "workday":
                resp = await client.post(r.url, json={"appliedFacets": {}, "limit": 1, "offset": 0, "searchText": ""})
            else:
                resp = await client.get(r.url)
            r.status = resp.status_code
            if resp.status_code == 200:
                r.jobs = count_jobs(r.ats, resp.json())
        except Exception as e:  # network errors, bad JSON
            r.error = f"{type(e).__name__}: {e}"[:120]
        await asyncio.sleep(0.25)


async def run_checks(results: list[BoardResult]) -> None:
    sem = asyncio.Semaphore(CONCURRENCY)
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=HEADERS, follow_redirects=True) as client:
        await asyncio.gather(*(check_one(client, sem, r) for r in results))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--bad", action="store_true", help="only print failing boards")
    parser.add_argument("--json", action="store_true", help="emit JSON")
    parser.add_argument("--workday", action="store_true", help="also check Workday boards (read-only search POST)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.WARNING)
    results = collect_boards(workday=args.workday)
    asyncio.run(run_checks(results))

    disabled = ScraperRegistry.get_disabled() if hasattr(ScraperRegistry, "get_disabled") else {}
    ok = [r for r in results if r.ok]
    bad = [r for r in results if not r.ok]

    if args.json:
        print(json.dumps({
            "checked": len(results),
            "working": len(ok),
            "failing": len(bad),
            "disabled": sorted(disabled),
            "results": [asdict(r) for r in results],
        }, indent=2))
        return 0 if not bad else 1

    rows = bad if args.bad else results
    for r in sorted(rows, key=lambda x: (x.ok, x.ats, x.company_slug)):
        state = "OK " if r.ok else "BAD"
        detail = r.error or f"{r.status} jobs={r.jobs if r.jobs is not None else '-'}"
        print(f"{state} {r.company_slug:<24} {r.ats:<15} {r.board:<28} {detail}")

    print()
    print(f"Registered scrapers: {ScraperRegistry.count()}  |  disabled (not registered): {len(disabled)}")
    print(f"ATS boards checked: {len(results)}  |  working: {len(ok)}  |  failing: {len(bad)}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main())
