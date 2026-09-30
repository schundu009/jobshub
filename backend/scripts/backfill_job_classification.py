"""
Backfill classification + freshness + location on existing rows.

jobs:          employment_type, first_seen_at, effective_posted_at, reposted_count,
               is_evergreen / evergreen_reason, country_codes
contract_jobs: country_codes, effective_posted_at

    cd backend
    DATABASE_URL=postgresql://... python -m scripts.backfill_job_classification            # dry run (default)
    python -m scripts.backfill_job_classification --apply
    python -m scripts.backfill_job_classification --apply --only-unclassified

Walks each table by id in batches of 1000. The dry run never writes: values
are computed without touching the ORM objects and, on PostgreSQL, each batch
runs in a READ ONLY transaction. Prints a distribution summary (employment
types, evergreen reasons, active jobs per country, % unknown location and the
most common location strings that came back unknown).

Contract rows only get employment_type here (so /api/jobs hides them); moving
them into contract_jobs is contracts/scripts/migrate_contract_rows.py.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Importing database.py would otherwise run the app's early ALTER TABLE migrations.
import os  # noqa: E402
os.environ.setdefault("SKIP_EARLY_MIGRATIONS", "1")

BATCH = 1000


def _begin_batch(db, apply: bool) -> None:
    if not apply and db.get_bind().dialect.name == "postgresql":
        from sqlalchemy import text
        db.execute(text("SET TRANSACTION READ ONLY"))


def _end_batch(db, apply: bool) -> None:
    if apply:
        db.commit()
    else:
        db.rollback()
    db.expunge_all()


def _date(d):
    if d is None or isinstance(d, datetime):
        return d
    return datetime(d.year, d.month, d.day)


_NEW_JOB_COLUMNS = ("employment_type", "first_seen_at", "effective_posted_at", "reposted_count",
                    "is_evergreen", "evergreen_reason", "country_codes")


def backfill_jobs(db, apply: bool, only_unclassified: bool, batch: int, now: datetime, out) -> dict:
    from sqlalchemy import inspect
    from contracts.classifier import contract_routing
    from models import Job
    from services.job_freshness import effective_posted_at, evergreen_status, listed_days
    from services.job_location import from_country_codes, job_countries, to_country_codes

    # Works before the app migration ran (read-only dry run against prod): only
    # select the new columns when they exist.
    existing = {c["name"] for c in inspect(db.get_bind()).get_columns("jobs")}
    have_new = all(c in existing for c in _NEW_JOB_COLUMNS)
    if apply and not have_new:
        raise SystemExit("jobs table lacks the new columns - deploy/run the app migration before --apply")
    base_cols = [Job.id, Job.title, Job.job_description, Job.location, Job.posted_date, Job.created_at,
                 Job.date_found, Job.is_active]
    new_cols = [getattr(Job, c) for c in _NEW_JOB_COLUMNS] if have_new else []

    types: Counter = Counter()
    routed: Counter = Counter()
    evergreen: Counter = Counter()
    countries: Counter = Counter()
    unknown_locations: Counter = Counter()
    scanned = changed = active = active_unknown = 0
    last_id = 0
    while True:
        _begin_batch(db, apply)
        q = db.query(*base_cols, *new_cols).filter(Job.id > last_id)
        if only_unclassified and have_new:
            q = q.filter(Job.employment_type.is_(None))
        rows = q.order_by(Job.id).limit(batch).all()
        if not rows:
            db.rollback()
            break
        updates = []
        for row in rows:
            scanned += 1
            cur = dict(zip(_NEW_JOB_COLUMNS, row[len(base_cols):])) if have_new else {}
            route, et = contract_routing(row.title, row.job_description)
            new = {"employment_type": et or cur.get("employment_type")}
            if route:
                routed[new["employment_type"]] += 1
            first_seen = cur.get("first_seen_at") or row.created_at or _date(row.date_found)
            new["first_seen_at"] = first_seen
            eff = effective_posted_at(effective_posted_at(cur.get("effective_posted_at"), row.posted_date), first_seen)
            new["effective_posted_at"] = eff
            new["reposted_count"] = cur.get("reposted_count") or 0
            new["is_evergreen"], new["evergreen_reason"] = evergreen_status(
                row.title, row.job_description, listed_days(eff, now), new["reposted_count"])
            new["country_codes"] = to_country_codes(job_countries(row.location, row.title))
            if not have_new or any(cur.get(k) != v for k, v in new.items()):
                changed += 1
                updates.append({"id": row.id, **new})
            types[new["employment_type"] or "unknown"] += 1
            if new["is_evergreen"]:
                evergreen[new["evergreen_reason"]] += 1
            if row.is_active and not route:
                active += 1
                codes = from_country_codes(new["country_codes"])
                if not codes:
                    active_unknown += 1
                    unknown_locations[(row.location or "").strip() or "(empty)"] += 1
                for c in codes:
                    countries[c] += 1
        last_id = rows[-1].id
        if apply and updates:
            db.bulk_update_mappings(Job, updates)
        _end_batch(db, apply)
        out(f"  jobs: scanned {scanned} (last id {last_id})")
    return {
        "scanned": scanned, "changed": changed,
        "employment_type": dict(types.most_common()),
        "contract_rows": sum(routed.values()),
        "contract_rows_by_type": dict(routed.most_common()),
        "evergreen": dict(evergreen.most_common()),
        "active": active, "active_unknown_location": active_unknown,
        "top_countries": countries.most_common(15),
        "top_unknown_locations": unknown_locations.most_common(20),
    }


def backfill_contract_jobs(db, apply: bool, batch: int, out) -> dict:
    try:
        from contracts.models import ContractJob
        from sqlalchemy import inspect
        if not inspect(db.get_bind()).has_table("contract_jobs"):
            return {"scanned": 0, "changed": 0}
    except Exception:
        return {"scanned": 0, "changed": 0}
    from services.job_freshness import effective_posted_at
    from services.job_location import job_countries, to_country_codes

    scanned = changed = 0
    countries: Counter = Counter()
    last_id = 0
    while True:
        _begin_batch(db, apply)
        with db.no_autoflush:
            rows = db.query(ContractJob).filter(ContractJob.id > last_id).order_by(ContractJob.id).limit(batch).all()
            if not rows:
                db.rollback()
                break
            for job in rows:
                scanned += 1
                new = {
                    "country_codes": to_country_codes(job_countries(job.location, job.title)),
                    "effective_posted_at": effective_posted_at(job.posted_date, job.first_seen_at) or job.effective_posted_at,
                }
                if any(getattr(job, k) != v for k, v in new.items()):
                    changed += 1
                    if apply:
                        for k, v in new.items():
                            setattr(job, k, v)
                if job.is_active:
                    for c in (new["country_codes"] or "").split(","):
                        if c:
                            countries[c] += 1
            last_id = rows[-1].id
        _end_batch(db, apply)
        out(f"  contract_jobs: scanned {scanned} (last id {last_id})")
    return {"scanned": scanned, "changed": changed, "top_countries": countries.most_common(15)}


def backfill(db, apply: bool = False, only_unclassified: bool = False, batch: int = BATCH,
             now: datetime | None = None, out=print) -> dict:
    now = now or datetime.utcnow()
    jobs = backfill_jobs(db, apply, only_unclassified, batch, now, out)
    contracts = backfill_contract_jobs(db, apply, batch, out)
    mode = "apply" if apply else "dry-run (no writes)"
    verb = "changed" if apply else "would change"
    out(f"\n=== {mode} ===")
    out(f"jobs: scanned {jobs['scanned']}, {verb} {jobs['changed']}")
    out("  employment_type: " + ", ".join(f"{k}={v}" for k, v in jobs["employment_type"].items()))
    out(f"  contract rows (move with migrate_contract_rows): {jobs['contract_rows']} "
        f"({', '.join(f'{k}={v}' for k, v in jobs['contract_rows_by_type'].items()) or 'none'})")
    out("  evergreen: " + (", ".join(f"{k}={v}" for k, v in jobs["evergreen"].items()) or "none"))
    pct = (100.0 * jobs["active_unknown_location"] / jobs["active"]) if jobs["active"] else 0.0
    out(f"  active (non-contract) jobs: {jobs['active']}, unknown country: {jobs['active_unknown_location']} ({pct:.1f}%)")
    out("  top countries: " + (", ".join(f"{c}={n}" for c, n in jobs["top_countries"]) or "none"))
    out("  most common unknown locations:")
    for loc, n in jobs["top_unknown_locations"]:
        out(f"    {n:>6}  {loc[:100]}")
    out(f"contract_jobs: scanned {contracts['scanned']}, {verb} {contracts['changed']}")
    return {"mode": "apply" if apply else "dry-run", "jobs": jobs, "contract_jobs": contracts}


def main(argv=None, db=None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="report only, no writes (default)")
    mode.add_argument("--apply", action="store_true", help="write changes")
    parser.add_argument("--only-unclassified", action="store_true", help="jobs with employment_type IS NULL only")
    parser.add_argument("--batch", type=int, default=BATCH)
    args = parser.parse_args(argv)
    own = db is None
    if own:
        from database import SessionLocal  # DATABASE_URL from the environment (config.settings)
        db = SessionLocal()
    try:
        return backfill(db, apply=args.apply, only_unclassified=args.only_unclassified, batch=args.batch)
    finally:
        if own:
            db.close()


if __name__ == "__main__":
    main()
