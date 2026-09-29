#!/usr/bin/env python
"""
Merge duplicate shared companies ('roblox' / 'Roblox', 'Snap' / 'Snap Inc.',
'Apply.Careers.Microsoft.Com' / 'Microsoft', ...) into one row each.

Companies are grouped by services.company_resolver.normalize_company_key among
shared rows (user_id IS NULL; users' private companies are never touched).
For each group:
  - canonical row: the one named exactly like a registry scraper's
    ScraperConfig.company_name, else the one with the most jobs, else lowest id
  - every column referencing companies.id (found by reflection: jobs,
    contacts, ingestion_sources, ...) is re-pointed to the canonical row
  - jobs that would collide on (company_id, external_job_id) are merged: the
    job carrying user data (owner / non-wishlist status / description) is kept,
    the other's children (notes, interviews, documents, scores, submissions...)
    are moved onto it and the other job is deleted
  - the duplicate company rows are deleted
  - the canonical row is renamed to the registry's company_name if different
Single rows whose name differs from the registry's name for their key are
renamed too (so scraper stats find them).

Idempotent: a second run finds nothing to do.

Usage (from backend/):
    python scripts/merge_duplicate_companies.py            # dry run: print the plan
    python scripts/merge_duplicate_companies.py --apply    # execute in one transaction
    DATABASE_URL=postgresql://... python scripts/merge_duplicate_companies.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# This script never needs the app's startup migrations.
os.environ.setdefault("SKIP_EARLY_MIGRATIONS", "1")
os.environ.setdefault("SKIP_MIGRATIONS", "1")

from sqlalchemy import MetaData, Table, and_, func, select  # noqa: E402
from sqlalchemy.engine import Connection  # noqa: E402

from services.company_resolver import normalize_company_key  # noqa: E402


@dataclass
class Group:
    key: str
    canonical_id: int
    canonical_name: str
    rename_to: Optional[str]
    duplicates: list[tuple[int, str, int]] = field(default_factory=list)  # (id, name, jobs)
    canonical_jobs: int = 0


def _registry_names() -> dict[str, str]:
    try:
        from services.company_resolver import registry_display_names
        return registry_display_names()
    except Exception as e:  # registry import problems shouldn't block a merge
        print(f"warning: scraper registry unavailable ({e}); canonical = most jobs", file=sys.stderr)
        return {}


def _references(metadata: MetaData, target_table: str, fallback_column: str) -> list[tuple[Table, str]]:
    """(table, column) pairs that point at target_table.id (FKs, or a column named fallback_column)."""
    refs = []
    for table in metadata.sorted_tables:
        if table.name == target_table:
            continue
        for column in table.columns:
            is_fk = any(fk.column.table.name == target_table for fk in column.foreign_keys)
            if is_fk or column.name == fallback_column:
                refs.append((table, column.name))
    return refs


def plan(conn: Connection, registry_names: Optional[dict[str, str]] = None) -> list[Group]:
    metadata = MetaData()
    metadata.reflect(bind=conn, only=["companies", "jobs"])
    companies, jobs = metadata.tables["companies"], metadata.tables["jobs"]
    names = _registry_names() if registry_names is None else registry_names

    job_counts = dict(conn.execute(
        select(jobs.c.company_id, func.count()).where(jobs.c.company_id.isnot(None)).group_by(jobs.c.company_id)
    ).all())

    by_key: dict[str, list[tuple[int, str]]] = {}
    for cid, cname in conn.execute(
        select(companies.c.id, companies.c.name).where(companies.c.user_id.is_(None)).order_by(companies.c.id)
    ).all():
        key = normalize_company_key(cname)
        if key:
            by_key.setdefault(key, []).append((cid, cname))

    groups = []
    for key, rows in sorted(by_key.items()):
        registry_name = names.get(key)
        exact = [r for r in rows if registry_name and r[1] == registry_name]
        if exact:
            canonical = exact[0]
        else:
            canonical = max(rows, key=lambda r: (job_counts.get(r[0], 0), -r[0]))
        rename_to = registry_name if registry_name and canonical[1] != registry_name else None
        dups = [(cid, cname, job_counts.get(cid, 0)) for cid, cname in rows if cid != canonical[0]]
        if dups or rename_to:
            groups.append(Group(
                key=key, canonical_id=canonical[0], canonical_name=canonical[1], rename_to=rename_to,
                duplicates=dups, canonical_jobs=job_counts.get(canonical[0], 0),
            ))
    return groups


def _keep_score(job) -> tuple:
    """Higher = more worth keeping when two rows are the same posting."""
    return (
        job.user_id is not None,
        (job.status or "wishlist") != "wishlist",
        bool(job.job_description),
        bool(job.is_active),
        str(job.updated_at or ""),
    )


def apply(conn: Connection, groups: list[Group]) -> dict:
    """Execute the plan on ``conn`` (caller owns the transaction)."""
    metadata = MetaData()
    metadata.reflect(bind=conn)
    companies, jobs = metadata.tables["companies"], metadata.tables["jobs"]
    company_refs = [(t, c) for t, c in _references(metadata, "companies", "company_id") if t.name != "jobs"]
    job_refs = _references(metadata, "jobs", "job_id")

    stats = {"companies_deleted": 0, "companies_renamed": 0, "jobs_moved": 0,
             "jobs_merged": 0, "rows_repointed": 0}

    def move_job_children(from_job: int, to_job: int) -> None:
        for table, column in job_refs:
            result = conn.execute(
                table.update().where(table.c[column] == from_job).values({column: to_job})
            )
            stats["rows_repointed"] += result.rowcount or 0

    for group in groups:
        target = group.canonical_id
        for dup_id, _, _ in group.duplicates:
            # Jobs: merge postings that already exist under the canonical row.
            dup_jobs = conn.execute(select(jobs).where(jobs.c.company_id == dup_id)).all()
            for job in dup_jobs:
                twin = None
                if job.external_job_id:
                    twin = conn.execute(select(jobs).where(and_(
                        jobs.c.company_id == target,
                        jobs.c.external_job_id == job.external_job_id,
                    ))).first()
                if twin is None:
                    conn.execute(jobs.update().where(jobs.c.id == job.id).values(company_id=target))
                    stats["jobs_moved"] += 1
                    continue
                if job.user_id is not None and twin.user_id is not None and job.user_id != twin.user_id:
                    # Two users' own copies: keep both, de-collide the external id.
                    conn.execute(jobs.update().where(jobs.c.id == job.id).values(
                        company_id=target, external_job_id=f"{job.external_job_id}#dup{job.id}"[:255],
                    ))
                    stats["jobs_moved"] += 1
                    continue
                keep, drop = (job, twin) if _keep_score(job) > _keep_score(twin) else (twin, job)
                move_job_children(drop.id, keep.id)
                conn.execute(jobs.delete().where(jobs.c.id == drop.id))
                if keep.id == job.id:
                    conn.execute(jobs.update().where(jobs.c.id == job.id).values(company_id=target))
                stats["jobs_merged"] += 1

            for table, column in company_refs:
                result = conn.execute(
                    table.update().where(table.c[column] == dup_id).values({column: target})
                )
                stats["rows_repointed"] += result.rowcount or 0

            conn.execute(companies.delete().where(companies.c.id == dup_id))
            stats["companies_deleted"] += 1

        if group.rename_to:
            conn.execute(companies.update().where(companies.c.id == target).values(name=group.rename_to))
            stats["companies_renamed"] += 1

    return stats


def format_plan(groups: list[Group]) -> str:
    if not groups:
        return "No duplicate companies found."
    lines = []
    merges = [g for g in groups if g.duplicates]
    renames = [g for g in groups if g.rename_to and not g.duplicates]
    for g in merges:
        target = f"#{g.canonical_id} '{g.canonical_name}' ({g.canonical_jobs} jobs)"
        if g.rename_to:
            target += f" -> rename '{g.rename_to}'"
        dups = ", ".join(f"#{cid} '{name}' ({n} jobs)" for cid, name, n in g.duplicates)
        lines.append(f"[{g.key}] keep {target}; merge {dups}")
    for g in renames:
        lines.append(f"[{g.key}] rename #{g.canonical_id} '{g.canonical_name}' -> '{g.rename_to}'")
    moved = sum(n for g in merges for _, _, n in g.duplicates)
    lines.append(
        f"\n{len(merges)} groups, {sum(len(g.duplicates) for g in merges)} duplicate rows to delete, "
        f"{moved} jobs to re-point, {sum(1 for g in groups if g.rename_to)} renames."
    )
    return "\n".join(lines)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="print the plan (default)")
    mode.add_argument("--apply", action="store_true", help="execute the plan in one transaction")
    parser.add_argument("--database-url", default=None, help="defaults to DATABASE_URL / app config")
    args = parser.parse_args(argv)

    if args.database_url:
        from sqlalchemy import create_engine
        engine = create_engine(args.database_url)
    else:
        from database import engine
        if engine is None:
            print("No database engine (check DATABASE_URL)", file=sys.stderr)
            return 2

    with engine.connect() as conn:
        groups = plan(conn)
        print(format_plan(groups))
    if not args.apply or not groups:
        if groups:
            print("\nDry run - nothing changed. Re-run with --apply to execute.")
        return 0

    with engine.begin() as conn:  # one transaction; rolls back on any error
        groups = plan(conn)
        stats = apply(conn, groups)
    print(f"\nApplied: {stats}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
