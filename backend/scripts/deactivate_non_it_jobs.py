#!/usr/bin/env python
"""
Retire non-IT jobs: mark active scraped jobs whose title is confidently not an
IT/tech role inactive (services.it_roles, ambiguous titles kept). Jobs users
added themselves are never touched. The same sweep runs daily in Celery
(tasks.maintenance_tasks.deactivate_non_it_jobs); this is for a first run and
for checking what it would do.

Usage (from backend/):
    python -m scripts.deactivate_non_it_jobs            # dry run: counts + top titles
    python -m scripts.deactivate_non_it_jobs --apply    # deactivate
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SKIP_EARLY_MIGRATIONS", "1")
os.environ.setdefault("SKIP_MIGRATIONS", "1")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="deactivate (default: dry run)")
    args = parser.parse_args()

    from database import SessionLocal
    from tasks.maintenance_tasks import deactivate_non_it_rows

    db = SessionLocal()
    try:
        result = deactivate_non_it_rows(db, apply=args.apply)
    finally:
        db.close()

    verb = "Deactivated" if args.apply else "Would deactivate"
    share = (100.0 * result["non_it"] / result["checked"]) if result["checked"] else 0.0
    print(f"{verb} {result['non_it']:,} of {result['checked']:,} active scraped jobs ({share:.1f}%) as non-IT")
    print("Most common titles:")
    for title, n in result["top_titles"]:
        print(f"  {n:5d}  {title}")


if __name__ == "__main__":
    main()
