"""
Fill missing pay from descriptions on existing rows.

jobs:          salary_min / salary_max / hourly_rate_min / hourly_rate_max (services.salary)
contract_jobs: pay_rate_min / pay_rate_max / pay_period / hourly_rate_min / hourly_rate_max

Only rows with no pay at all are touched; a stored value is never replaced.

    cd backend
    DATABASE_URL=postgresql://... python -m scripts.backfill_pay            # dry run (default)
    python -m scripts.backfill_pay --apply

Walks each table by id in batches of 1000; the dry run never writes (READ ONLY
transactions on PostgreSQL).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Importing database.py would otherwise run the app's early ALTER TABLE migrations.
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


def backfill_jobs(db, apply: bool, batch: int, out) -> dict:
    from models import Job
    from services.salary import pay_from_text

    scanned = filled = 0
    last_id = 0
    while True:
        _begin_batch(db, apply)
        rows = (db.query(Job.id, Job.job_description)
                .filter(Job.id > last_id, Job.salary_min.is_(None), Job.salary_max.is_(None),
                        Job.job_description.isnot(None))
                .order_by(Job.id).limit(batch).all())
        if not rows:
            db.rollback()
            break
        updates = []
        for row in rows:
            scanned += 1
            pay = pay_from_text(row.job_description)
            if pay["salary_min"] is not None:
                updates.append({"id": row.id, **pay})
        filled += len(updates)
        last_id = rows[-1].id
        if apply and updates:
            db.bulk_update_mappings(Job, updates)
        _end_batch(db, apply)
        out(f"  jobs: scanned {scanned}, filled {filled} (last id {last_id})")
    return {"scanned": scanned, "filled": filled}


def backfill_contract_jobs(db, apply: bool, batch: int, out) -> dict:
    from sqlalchemy import inspect
    from contracts.models import ContractJob
    from contracts.service import fill_pay

    if not inspect(db.get_bind()).has_table("contract_jobs"):
        return {"scanned": 0, "filled": 0}
    scanned = filled = 0
    last_id = 0
    while True:
        _begin_batch(db, apply)
        with db.no_autoflush:
            rows = (db.query(ContractJob)
                    .filter(ContractJob.id > last_id, ContractJob.pay_period.is_(None),
                            ContractJob.pay_rate_min.is_(None), ContractJob.pay_rate_max.is_(None))
                    .order_by(ContractJob.id).limit(batch).all())
            if not rows:
                db.rollback()
                break
            for job in rows:
                scanned += 1
                if fill_pay(job):
                    filled += 1
            last_id = rows[-1].id
        _end_batch(db, apply)
        out(f"  contract_jobs: scanned {scanned}, filled {filled} (last id {last_id})")
    return {"scanned": scanned, "filled": filled}


def backfill(db, apply: bool = False, batch: int = BATCH, out=print) -> dict:
    jobs = backfill_jobs(db, apply, batch, out)
    contracts = backfill_contract_jobs(db, apply, batch, out)
    verb = "filled" if apply else "would fill"
    out(f"\n=== {'apply' if apply else 'dry-run (no writes)'} ===")
    out(f"jobs: scanned {jobs['scanned']} without salary, {verb} {jobs['filled']}")
    out(f"contract_jobs: scanned {contracts['scanned']} without pay, {verb} {contracts['filled']}")
    return {"jobs": jobs, "contract_jobs": contracts}


def main(argv=None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    parser.add_argument("--batch", type=int, default=BATCH)
    args = parser.parse_args(argv)
    from database import SessionLocal  # DATABASE_URL from the environment (config.settings)
    db = SessionLocal()
    try:
        return backfill(db, apply=args.apply, batch=args.batch)
    finally:
        db.close()


if __name__ == "__main__":
    main()
