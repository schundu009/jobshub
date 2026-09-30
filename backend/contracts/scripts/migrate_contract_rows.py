"""
Move contract roles that were stored in jobs into contract_jobs.

    cd backend
    python -m contracts.scripts.migrate_contract_rows            # dry run (default)
    python -m contracts.scripts.migrate_contract_rows --apply

Scans active shared jobs (user_id IS NULL) by id in batches of 1000; a row that
contracts.classifier calls contract / contract_to_hire / temporary / freelance
is saved to contract_jobs (same 30-day window as live saves) and the jobs row
is deactivated (never deleted: users' applications/notes may point at it).
The dry run only reads and counts.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import os  # noqa: E402
os.environ.setdefault("SKIP_EARLY_MIGRATIONS", "1")

BATCH = 1000
AGGREGATOR_SOURCES = {"themuse", "remoteok", "arbeitnow", "linkedin", "indeed", "glassdoor",
                      "apify_linkedin", "apify_indeed"}


def migrate(db, apply: bool = False, batch: int = BATCH, out=print) -> dict:
    from contracts.classifier import contract_routing
    from contracts.service import contract_max_age_days, save_contract_jobs
    from models import Job
    from scrapers.base import ScrapedJob

    found: Counter = Counter()
    moved = skipped_old = deactivated = scanned = 0
    last_id = 0
    while True:
        rows = (db.query(Job).filter(Job.id > last_id, Job.is_active == True, Job.user_id.is_(None))  # noqa: E712
                .order_by(Job.id).limit(batch).all())
        if not rows:
            break
        by_source = defaultdict(list)
        for job in rows:
            scanned += 1
            route, et = contract_routing(job.title, job.job_description,
                                         {"employment_type": job.employment_type})
            if not route:
                continue
            found[et] += 1
            by_source[(job.source or "unknown", job.company_id)].append((job, et))
        for (source, company_id), items in by_source.items():
            scraped = [ScrapedJob(title=j.title, location=j.location or "", job_url=j.job_url or "",
                                  external_job_id=j.external_job_id or f"job-{j.id}",
                                  job_description=j.job_description,
                                  posted_date=min(d for d in (j.posted_date, j.first_seen_at, j.created_at) if d)
                                  if (j.posted_date or j.first_seen_at or j.created_at) else None,
                                  employment_type_raw=et)
                       for j, et in items]
            if not apply:  # dry run: count only, never write
                cutoff = datetime.utcnow() - timedelta(days=contract_max_age_days(db))
                for s in scraped:
                    if s.posted_date and s.posted_date < cutoff:
                        skipped_old += 1
                    else:
                        moved += 1
                deactivated += len(items)
                continue
            result = save_contract_jobs(
                db, source, scraped,
                source_type="aggregator" if source in AGGREGATOR_SOURCES else "company_board",
                company_id=company_id, commit=False)
            moved += result.saved
            skipped_old += result.skipped_old
            for j, et in items:
                j.employment_type = et
                j.is_active = False
                deactivated += 1
        last_id = rows[-1].id
        if apply:
            db.commit()
        else:
            db.rollback()
        db.expunge_all()
        out(f"  ... scanned {scanned} (last id {last_id})")

    summary = {"mode": "apply" if apply else "dry-run", "scanned": scanned, "contract_rows": sum(found.values()),
               "by_type": dict(found), "moved": moved, "skipped_old": skipped_old, "deactivated": deactivated}
    out(f"\n{summary['mode']}: scanned {scanned} active jobs, {summary['contract_rows']} contract rows "
        f"({', '.join(f'{k}={v}' for k, v in found.items()) or 'none'})")
    out(f"  -> contract_jobs: {moved} saved, {skipped_old} older than the contract window (not moved)")
    out(f"  -> jobs rows deactivated: {deactivated}")
    return summary


def main(argv=None, db=None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--batch", type=int, default=BATCH)
    args = parser.parse_args(argv)
    own = db is None
    if own:
        from database import SessionLocal
        import contracts.models  # noqa: F401
        db = SessionLocal()
    try:
        return migrate(db, apply=args.apply, batch=args.batch)
    finally:
        if own:
            db.close()


if __name__ == "__main__":
    main()
