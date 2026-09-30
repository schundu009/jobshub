"""
Deactivate active contract_jobs rows that are not IT / tech roles.

    cd backend
    python -m contracts.scripts.deactivate_non_it            # dry run (default)
    python -m contracts.scripts.deactivate_non_it --apply
    python -m contracts.scripts.deactivate_non_it --include-uncertain   # also lean-out / undecided

Uses services.it_roles on the stored title and skills with the same rule as the
save path's safety net: only confident non-IT decisions (reason title_out /
qualifier_out / context_out) are deactivated; lean-out and undecided titles are
kept unless --include-uncertain. Rows are only deactivated (is_active=False),
never deleted. Prints counts by source and IT category, plus a sample of the
titles it would drop per source.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import os  # noqa: E402
os.environ.setdefault("SKIP_EARLY_MIGRATIONS", "1")

BATCH = 1000
SAMPLE = 8


def run(db, apply: bool = False, strict: bool = False, batch: int = BATCH, out=print) -> dict:
    from contracts.models import ContractJob
    from services.it_roles import classify_it

    by_source: dict[str, Counter] = defaultdict(Counter)
    categories: Counter = Counter()
    samples: dict[str, list[str]] = defaultdict(list)
    scanned = dropped = 0
    last_id = 0
    while True:
        rows = (db.query(ContractJob)
                .filter(ContractJob.id > last_id, ContractJob.is_active == True)  # noqa: E712
                .order_by(ContractJob.id).limit(batch).all())
        if not rows:
            break
        for row in rows:
            scanned += 1
            c = by_source[row.source or "unknown"]
            c["active"] += 1
            d = classify_it(row.title, skills=row.skills if isinstance(row.skills, list) else None)
            from contracts.service import CONFIDENT_NON_IT
            confident_out = d.is_it is False and d.reason in CONFIDENT_NON_IT
            keep = not (confident_out or (strict and not d.is_it))
            if keep:
                c["it"] += 1
                categories[d.category or "undecided"] += 1
                if not d.is_it:
                    c["undecided_kept"] += 1
                continue
            c["non_it"] += 1
            dropped += 1
            if len(samples[row.source]) < SAMPLE:
                samples[row.source].append(row.title)
            if apply:
                row.is_active = False
        last_id = rows[-1].id
        if apply:
            db.commit()
        else:
            db.rollback()
        db.expunge_all()

    mode = "apply" if apply else "dry-run"
    out(f"{mode}{' (incl. uncertain)' if strict else ''}: {scanned} active contract rows, {dropped} non-IT "
        f"{'deactivated' if apply else 'would be deactivated'}")
    out(f"  {'source':<24}{'active':>8}{'IT':>7}{'non-IT':>8}{'uncertain kept':>16}")
    for source, c in sorted(by_source.items(), key=lambda kv: -kv[1]["non_it"]):
        out(f"  {source:<24}{c['active']:>8}{c['it']:>7}{c['non_it']:>8}{c['undecided_kept']:>16}")
    out("  kept by IT category: " + ", ".join(f"{k}={v}" for k, v in categories.most_common()))
    for source, titles in samples.items():
        out(f"  e.g. {source}: " + " | ".join(titles))
    return {"mode": mode, "scanned": scanned, "non_it": dropped,
            "by_source": {k: dict(v) for k, v in by_source.items()}, "categories": dict(categories)}


def main(argv=None, db=None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--include-uncertain", action="store_true",
                        help="also deactivate lean-out / undecided titles")
    parser.add_argument("--batch", type=int, default=BATCH)
    args = parser.parse_args(argv)
    own = db is None
    if own:
        from database import SessionLocal
        import contracts.models  # noqa: F401
        db = SessionLocal()
    try:
        return run(db, apply=args.apply, strict=args.include_uncertain, batch=args.batch)
    finally:
        if own:
            db.close()


if __name__ == "__main__":
    main()
