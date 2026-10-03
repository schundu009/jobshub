"""
Per-board scraper health, derived from scraper_runs.

For every enabled board (coded scrapers and job_boards rows): when it last
succeeded, what its last two runs found, and how many runs in a row failed.
A board is stale with no success in STALE_HOURS, failing after
FAILING_AFTER consecutive failures. Used by GET /api/scrapers/health and the
scraper health alert.
"""

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from models import ScraperConfigDB, ScraperRun
from scrapers.board_scraper import ats_of
from scrapers.registry import ScraperRegistry

STALE_HOURS = 48
FAILING_AFTER = 3
_RECENT_RUNS = 20  # runs per board read to count consecutive failures


def enabled_boards(db: Session) -> dict[str, str]:
    """slug -> ATS for every scraper the scheduler runs (not disabled in code or config)."""
    disabled = {c.company_slug for c in db.query(ScraperConfigDB.company_slug).filter(
        ScraperConfigDB.is_enabled == False).all()}  # noqa: E712
    boards = {}
    for slug in ScraperRegistry.list_slugs() + ScraperRegistry.list_board_slugs():
        if slug in disabled:
            continue
        cls = ScraperRegistry.get(slug)
        if cls is not None:
            boards[slug] = ats_of(cls)
    return boards


def board_health(db: Session, boards: dict[str, str], now: Optional[datetime] = None) -> list[dict]:
    """One freshness record per board, in a fixed number of queries."""
    now = now or datetime.utcnow()
    slugs = list(boards)
    if not slugs:
        return []

    last_success = dict(db.query(ScraperRun.company_slug, func.max(ScraperRun.run_at)).filter(
        ScraperRun.company_slug.in_(slugs), ScraperRun.success == True,  # noqa: E712
    ).group_by(ScraperRun.company_slug).all())

    ranked = db.query(
        ScraperRun.company_slug.label("slug"),
        ScraperRun.success.label("success"),
        ScraperRun.jobs_found.label("jobs_found"),
        ScraperRun.run_at.label("run_at"),
        ScraperRun.error_message.label("error_message"),
        func.row_number().over(
            partition_by=ScraperRun.company_slug,
            order_by=(ScraperRun.run_at.desc(), ScraperRun.id.desc()),
        ).label("rn"),
    ).filter(ScraperRun.company_slug.in_(slugs)).subquery()
    recent: dict[str, list] = {}
    for row in db.query(ranked).filter(ranked.c.rn <= _RECENT_RUNS).order_by(ranked.c.slug, ranked.c.rn).all():
        recent.setdefault(row.slug, []).append(row)

    config_failures = dict(db.query(ScraperConfigDB.company_slug, ScraperConfigDB.consecutive_failures).filter(
        ScraperConfigDB.company_slug.in_(slugs)).all())

    stale_before = now - timedelta(hours=STALE_HOURS)
    out = []
    for slug in slugs:
        runs = recent.get(slug, [])
        failures = 0
        for run in runs:
            if run.success:
                break
            failures += 1
        if failures == len(runs) == _RECENT_RUNS:
            failures = max(failures, config_failures.get(slug) or 0)
        success_at = last_success.get(slug)
        last_error = next((r.error_message for r in runs if not r.success and r.error_message), None)
        meta = ScraperRegistry.get_metadata(slug) or {}
        out.append({
            "slug": slug,
            "company_name": meta.get("company_name") or slug,
            "ats": boards[slug],
            "last_success_at": success_at.isoformat() if success_at else None,
            "last_run_at": runs[0].run_at.isoformat() if runs and runs[0].run_at else None,
            "jobs_found_last": runs[0].jobs_found if runs else None,
            "jobs_found_previous": runs[1].jobs_found if len(runs) > 1 else None,
            "consecutive_failures": failures,
            "last_error": (last_error or "")[:300] or None,
            "stale": success_at is None or success_at < stale_before,
            "failing": failures >= FAILING_AFTER,
        })
    return out


def health_report(db: Session, now: Optional[datetime] = None) -> dict:
    """Stale boards, failing boards and counts by ATS."""
    now = now or datetime.utcnow()
    boards = enabled_boards(db)
    records = board_health(db, boards, now)
    by_ats: dict[str, dict] = {}
    for r in records:
        counts = by_ats.setdefault(r["ats"], {"boards": 0, "stale": 0, "failing": 0})
        counts["boards"] += 1
        counts["stale"] += r["stale"]
        counts["failing"] += r["failing"]
    return {
        "checked_at": now.isoformat(),
        "boards": len(records),
        "stale_hours": STALE_HOURS,
        "failing_after": FAILING_AFTER,
        "stale": sorted((r for r in records if r["stale"]), key=lambda r: r["last_success_at"] or ""),
        "failing": sorted((r for r in records if r["failing"]), key=lambda r: -r["consecutive_failures"]),
        "by_ats": dict(sorted(by_ats.items())),
    }
