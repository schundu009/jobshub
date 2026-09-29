#!/usr/bin/env python
"""
After the scraper-board repair: give every scraper that is enabled in code a
clean slate, and hide jobs from scrapers that are disabled in code.

For each registry-enabled slug (ScraperRegistry.list_slugs()) with a
ScraperConfigDB row:
  - is_enabled = True, consecutive_failures = 0
  - drop config_overrides.auto_disabled / auto_disabled_reason
  - drop config_overrides.url_override when the scraper is not a Greenhouse
    scraper (only GreenhouseMixin reads it; old auto-heal wrote Greenhouse
    URLs onto Ashby/Lever/Workday scrapers)
For each slug in ScraperRegistry.get_disabled():
  - jobs with source == slug and is_active = True -> is_active = False

Idempotent. Dry run by default.

Usage (from backend/):
    python scripts/reenable_repaired_scrapers.py            # print what would change
    python scripts/reenable_repaired_scrapers.py --apply    # execute in one transaction
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SKIP_EARLY_MIGRATIONS", "1")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from sqlalchemy.orm import Session  # noqa: E402


def _is_greenhouse(scraper_cls) -> bool:
    try:
        from scrapers.custom.remaining_scrapers import GreenhouseMixin
    except Exception:
        return False
    return issubclass(scraper_cls, GreenhouseMixin)


def plan_and_apply(db: Session, apply: bool = False, registry=None) -> dict:
    """Compute (and with apply=True, stage) the changes. Caller commits."""
    from models import Job, ScraperConfigDB

    if registry is None:
        from scrapers.registry import ScraperRegistry as registry

    enabled_slugs = registry.list_slugs()
    configs = {
        c.company_slug: c
        for c in db.query(ScraperConfigDB).filter(ScraperConfigDB.company_slug.in_(enabled_slugs)).all()
    } if enabled_slugs else {}

    reenabled = []
    for slug in enabled_slugs:
        cfg = configs.get(slug)
        if cfg is None:
            continue
        overrides = dict(cfg.config_overrides or {})
        changes = []
        if not cfg.is_enabled:
            changes.append("enable")
        if cfg.consecutive_failures:
            changes.append(f"failures {cfg.consecutive_failures}->0")
        for key in ("auto_disabled", "auto_disabled_reason"):
            if key in overrides:
                overrides.pop(key)
                changes.append(f"drop {key}")
        if "url_override" in overrides and not _is_greenhouse(registry.get(slug)):
            changes.append(f"drop url_override {overrides.pop('url_override')}")
        if not changes:
            continue
        reenabled.append({"slug": slug, "changes": changes})
        if apply:
            cfg.is_enabled = True
            cfg.consecutive_failures = 0
            cfg.config_overrides = overrides or None

    disabled_slugs = sorted(registry.get_disabled())
    deactivated = {}
    for slug in disabled_slugs:
        query = db.query(Job).filter(Job.source == slug, Job.is_active == True)  # noqa: E712
        count = query.count()
        if count:
            deactivated[slug] = count
            if apply:
                query.update({"is_active": False}, synchronize_session=False)

    return {"reenabled": reenabled, "deactivated_jobs": deactivated}


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="execute (default: dry run)")
    args = parser.parse_args(argv)

    from database import SessionLocal
    if SessionLocal is None:
        print("No database session (check DATABASE_URL)", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        result = plan_and_apply(db, apply=args.apply)
        for row in result["reenabled"]:
            print(f"scraper {row['slug']}: {', '.join(row['changes'])}")
        for slug, count in result["deactivated_jobs"].items():
            print(f"jobs from disabled scraper {slug}: deactivate {count}")
        if not result["reenabled"] and not result["deactivated_jobs"]:
            print("Nothing to change.")
        if args.apply:
            db.commit()
            try:
                from services.redis_service import redis_service
                redis_service.cache_delete("scrapers:status")
            except Exception:
                pass
            print(f"\nApplied: {len(result['reenabled'])} scrapers reset, "
                  f"{sum(result['deactivated_jobs'].values())} jobs deactivated.")
        else:
            print("\nDry run - nothing changed. Re-run with --apply to execute.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
