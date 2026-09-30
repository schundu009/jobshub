"""
Send company-board rows that are not contract roles back to jobs.

    cd backend
    python -m contracts.scripts.reroute_company_board_rows            # dry run (default)
    python -m contracts.scripts.reroute_company_board_rows --apply

Re-evaluates every ACTIVE contract_jobs row with source_type='company_board'
using the company-board rule (contracts.classifier.company_board_routing):
contract only when the title carries an explicit marker (Contract, Contractor,
C2H, Contract-to-Hire, Temp, Temporary, Freelance, 1099) or a stored raw ATS
employment field says so. The description is ignored. contract_jobs stores no
raw ATS field, so in practice the title decides; a row that really is a
contract by its ATS field is re-routed to contract_jobs by the next full-time
scrape (the save path upserts it and reactivates the contract row).

For each row that is NOT a contract:
- contract_jobs.is_active = False
- the matching jobs row (same source + external_job_id, deactivated earlier by
  migrate_contract_rows or the save path) is reactivated with the new
  employment label, if one exists; otherwise nothing - the next full-time
  scrape inserts it.
The dry run only reads and counts.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import os  # noqa: E402
os.environ.setdefault("SKIP_EARLY_MIGRATIONS", "1")

BATCH = 500


def _find_job(db, row):
    from models import Job
    ext = row.external_job_id
    q = db.query(Job).filter(Job.user_id.is_(None))
    job = q.filter(Job.source == row.source, Job.external_job_id == ext).order_by(Job.id.desc()).first()
    if job is None and row.company_id:
        job = q.filter(Job.company_id == row.company_id, Job.external_job_id == ext).order_by(Job.id.desc()).first()
    if job is None and ext.startswith("job-") and ext[4:].isdigit():
        # migrate_contract_rows used "job-<id>" when the jobs row had no external id
        job = q.filter(Job.id == int(ext[4:])).first()
    return job


def reroute(db, apply: bool = False, batch: int = BATCH, out=print) -> dict:
    from contracts.classifier import company_board_routing
    from contracts.models import ContractJob

    scanned = 0
    per_source: dict[str, Counter] = defaultdict(Counter)
    last_id = 0
    while True:
        rows = (db.query(ContractJob)
                .filter(ContractJob.id > last_id, ContractJob.is_active == True,  # noqa: E712
                        ContractJob.source_type == "company_board")
                .order_by(ContractJob.id).limit(batch).all())
        if not rows:
            break
        for row in rows:
            scanned += 1
            c = per_source[row.source or "unknown"]
            c["scanned"] += 1
            # Only the title (no raw ATS field is stored on contract_jobs); description ignored.
            route, et = company_board_routing(row.title, None, None)
            if route:
                c["kept"] += 1
                continue
            c["not_contract"] += 1
            job = _find_job(db, row)
            if job is None:
                c["no_jobs_row"] += 1
            elif job.is_active:
                c["jobs_row_already_active"] += 1
            else:
                c["jobs_reactivated"] += 1
            if apply:
                row.is_active = False
                if job is not None and not job.is_active:
                    job.is_active = True
                    job.employment_type = et
        last_id = rows[-1].id
        if apply:
            db.commit()
        else:
            db.rollback()
        db.expunge_all()

    total = Counter()
    for c in per_source.values():
        total.update(c)
    mode = "apply" if apply else "dry-run"
    out(f"{mode}: {scanned} active company_board contract rows")
    out(f"  {'source':<28}{'scanned':>8}{'kept':>7}{'->jobs':>8}{'reactiv':>9}{'no_row':>8}{'active':>8}")
    for source, c in sorted(per_source.items(), key=lambda kv: -kv[1]["not_contract"]):
        out(f"  {source:<28}{c['scanned']:>8}{c['kept']:>7}{c['not_contract']:>8}{c['jobs_reactivated']:>9}"
            f"{c['no_jobs_row']:>8}{c['jobs_row_already_active']:>8}")
    out(f"  {'TOTAL':<28}{total['scanned']:>8}{total['kept']:>7}{total['not_contract']:>8}"
        f"{total['jobs_reactivated']:>9}{total['no_jobs_row']:>8}{total['jobs_row_already_active']:>8}")
    if not apply:
        out("  (dry run: nothing written; re-run with --apply)")
    return {"mode": mode, "scanned": scanned, "totals": dict(total),
            "by_source": {k: dict(v) for k, v in per_source.items()}}


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
        return reroute(db, apply=args.apply, batch=args.batch)
    finally:
        if own:
            db.close()


if __name__ == "__main__":
    main()
