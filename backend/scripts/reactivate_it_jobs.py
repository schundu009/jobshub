#!/usr/bin/env python
"""
Undo IT-filter false negatives: re-activate scraped jobs the IT-only save
filter switched off (since it went live) that services.it_roles now
classifies as IT.

Only rows that look like save-filter deactivations are touched:
  - inactive, scraped (user_id NULL, source != 'manual'), not routed to contracts
  - updated since --since (the deactivation) and still listed recently
    (last_seen_at within --seen-days of --since), so jobs that dropped off their
    board or went stale are not revived.

Usage (from backend/):
    python -m scripts.reactivate_it_jobs                  # dry run
    python -m scripts.reactivate_it_jobs --apply
    python -m scripts.reactivate_it_jobs --since 2026-09-30T04:15:00
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("SKIP_EARLY_MIGRATIONS", "1")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

# The IT-only save filter (a9a1d72) went live shortly after 04:18 UTC.
DEFAULT_SINCE = "2026-09-30T04:15:00"
CONTRACT_TYPES = {"contract", "contract_to_hire", "c2c", "freelance", "contractor"}


def reactivate(db, since: datetime, seen_days: int = 2, apply: bool = False, batch: int = 2000) -> dict:
    from sqlalchemy import or_

    from models import Job
    from services.it_roles import is_it_role

    seen_floor = since - timedelta(days=seen_days)
    revived, titles, last_id = [], Counter(), 0
    while True:
        rows = db.query(Job.id, Job.title, Job.department, Job.employment_type).filter(
            Job.is_active == False,  # noqa: E712
            Job.user_id.is_(None),
            Job.source != "manual",
            Job.updated_at >= since,
            or_(Job.last_seen_at.is_(None), Job.last_seen_at >= seen_floor),
            Job.id > last_id,
        ).order_by(Job.id).limit(batch).all()
        if not rows:
            break
        last_id = rows[-1].id
        ids = [r.id for r in rows
               if (r.employment_type or "") not in CONTRACT_TYPES
               and is_it_role(r.title, department=r.department)]
        for r in rows:
            if r.id in ids:
                titles[r.title] += 1
        revived.extend(ids)
        if apply and ids:
            db.query(Job).filter(Job.id.in_(ids)).update({"is_active": True}, synchronize_session=False)
            db.commit()
    return {"reactivated": len(revived), "applied": apply, "top_titles": titles.most_common(30)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="re-activate (default: dry run)")
    parser.add_argument("--since", default=DEFAULT_SINCE, help="UTC ISO time the IT filter went live")
    parser.add_argument("--seen-days", type=int, default=2, help="require last_seen_at within N days before --since")
    args = parser.parse_args()

    from database import SessionLocal

    db = SessionLocal()
    try:
        result = reactivate(db, datetime.fromisoformat(args.since), args.seen_days, apply=args.apply)
    finally:
        db.close()
    verb = "Re-activated" if args.apply else "Would re-activate"
    print(f"{verb} {result['reactivated']:,} jobs now classified as IT")
    for title, n in result["top_titles"]:
        print(f"  {n:5d}  {title}")


if __name__ == "__main__":
    main()
