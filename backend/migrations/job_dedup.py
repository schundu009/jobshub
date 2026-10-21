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
