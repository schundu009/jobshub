"""
Backfill jobs.dedup_key (services.job_dedup) for rows saved before the column (idempotent).

New and edited rows get it from the save hook in models.py. The column and its
index come from migrations.job_classification. Called from main.run_migrations
under the startup advisory lock, in the background migration thread.
"""
import logging
from collections import defaultdict

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

BATCH = 1000


def backfill_dedup_key(connection, max_rows: int = 1_000_000, commit_batches: bool = False) -> int:
    """Key rows whose dedup_key is NULL, in id batches. Returns rows keyed."""
    from services.job_dedup import dedup_key

    if not inspect(connection).has_table("jobs"):
        return 0
    if "dedup_key" not in {c["name"] for c in inspect(connection).get_columns("jobs")}:
        return 0
    keyed, seen, last_id = 0, 0, 0
    while seen < max_rows:
        rows = connection.execute(text(
            "SELECT id, title, company_id, location, job_description FROM jobs "
            "WHERE dedup_key IS NULL AND id > :last ORDER BY id LIMIT :batch"
        ), {"last": last_id, "batch": BATCH}).fetchall()
        if not rows:
            break
        by_key: dict[str, list[int]] = defaultdict(list)
        for job_id, title, company_id, location, description in rows:
            key = dedup_key(title, company_id, location, description)
            if key:
                by_key[key].append(job_id)
        for key, ids in by_key.items():
            connection.execute(
                text(f"UPDATE jobs SET dedup_key = :k WHERE id IN ({','.join(str(int(i)) for i in ids)})"),
                {"k": key})
            keyed += len(ids)
        seen += len(rows)
        last_id = rows[-1][0]
        if commit_batches:  # short transactions: scrapers update these rows too
            connection.commit()
    if keyed:
        logger.info(f"Keyed {keyed} jobs for duplicate detection")
    return keyed


def backfill_pay_key(connection, max_rows: int = 1_000_000, commit_batches: bool = False) -> int:
    """Key rows with a pay range and no jobs.pay_key, newest first (the ones lists show). Returns rows keyed."""
    from services.job_dedup import pay_key

    if not inspect(connection).has_table("jobs"):
        return 0
    if "pay_key" not in {c["name"] for c in inspect(connection).get_columns("jobs")}:
        return 0
    keyed, seen, below = 0, 0, None
    while seen < max_rows:
        rows = connection.execute(text(
            "SELECT id, title, company_id, location, salary_min, salary_max FROM jobs "
            "WHERE pay_key IS NULL AND company_id IS NOT NULL "
            "AND (salary_min IS NOT NULL OR salary_max IS NOT NULL) "
            + ("AND id < :below " if below is not None else "")
            + "ORDER BY id DESC LIMIT :batch"
        ), {"below": below, "batch": BATCH}).fetchall()
        if not rows:
            break
        by_key: dict[str, list[int]] = defaultdict(list)
        for job_id, title, company_id, location, salary_min, salary_max in rows:
            key = pay_key(title, company_id, location, salary_min, salary_max)
            if key:
                by_key[key].append(job_id)
        for key, ids in by_key.items():
            connection.execute(
                text(f"UPDATE jobs SET pay_key = :k WHERE id IN ({','.join(str(int(i)) for i in ids)})"),
                {"k": key})
            keyed += len(ids)
        seen += len(rows)
        below = rows[-1][0]
        if commit_batches:
            connection.commit()
    if keyed:
        logger.info(f"Keyed {keyed} jobs by title, place and pay")
    return keyed

def rekey_office_code_titles(connection) -> int:
    """Re-key rows whose title ends in a parenthesised code ("(MTV)"), so pay_key's
    office-code rule reaches rows keyed before it. Only rows whose key changes are written."""
    from services.job_dedup import pay_key

    if not inspect(connection).has_table("jobs"):
        return 0
    rows = connection.execute(text(
        "SELECT id, title, company_id, location, salary_min, salary_max, pay_key FROM jobs "
        "WHERE pay_key IS NOT NULL AND title ~ '[(\\[][A-Z]{2,4}[)\\]]\\s*$'"
    )).fetchall()
    changed = 0
    for job_id, title, company_id, location, salary_min, salary_max, old in rows:
        key = pay_key(title, company_id, location, salary_min, salary_max)
        if key and key != old:
            connection.execute(text("UPDATE jobs SET pay_key = :k WHERE id = :id"), {"k": key, "id": job_id})
            changed += 1
    if changed:
        logger.info(f"Re-keyed {changed} jobs whose titles end in an office code")
    return changed
