"""
Add jobs.work_type (remote / hybrid / onsite, NULL = unknown) and backfill it (idempotent).

New and edited rows get it from the save hook in models.py; this fills rows
saved before the column existed. Called from main.run_migrations under the
startup advisory lock, in the background migration thread.
"""
import logging
from collections import defaultdict

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

BATCH = 1000


def migrate_job_work_type(connection, max_rows: int = 500_000, commit_batches: bool = False) -> int:
    """Add the column + index, then label rows still NULL. Returns rows labelled."""
    if not inspect(connection).has_table("jobs"):
        return 0
    postgres = connection.dialect.name == "postgresql"
    cols = {c["name"] for c in inspect(connection).get_columns("jobs")}
    if "work_type" not in cols:
        connection.execute(text(
            "ALTER TABLE jobs ADD COLUMN IF NOT EXISTS work_type VARCHAR(10)" if postgres
            else "ALTER TABLE jobs ADD COLUMN work_type VARCHAR(10)"))
        logger.info("Added jobs.work_type")
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_work_type ON jobs(work_type)"))
    if commit_batches:
        connection.commit()
    return backfill_work_type(connection, max_rows=max_rows, commit_batches=commit_batches)


def backfill_work_type(connection, max_rows: int = 500_000, commit_batches: bool = False) -> int:
    """Label rows whose work_type is NULL, in id batches (rows that stay unknown are re-read next start)."""
    from services.firm_matching import WORK_TYPE_DESC_CHARS, derive_work_type

    labelled, seen, last_id = 0, 0, 0
    while seen < max_rows:
        rows = connection.execute(text(
            "SELECT id, title, location, substr(job_description, 1, :n) FROM jobs "
            "WHERE work_type IS NULL AND id > :last ORDER BY id LIMIT :batch"
        ), {"n": WORK_TYPE_DESC_CHARS, "last": last_id, "batch": BATCH}).fetchall()
        if not rows:
            break
        by_value: dict[str, list[int]] = defaultdict(list)
        for job_id, title, location, desc in rows:
            value = derive_work_type(title, location, desc)
            if value:
                by_value[value].append(job_id)
        for value, ids in by_value.items():
            connection.execute(
                text(f"UPDATE jobs SET work_type = :v WHERE id IN ({','.join(str(int(i)) for i in ids)})"),
                {"v": value})
            labelled += len(ids)
        seen += len(rows)
        last_id = rows[-1][0]
        if commit_batches:  # short transactions: scrapers update these rows too
            connection.commit()
    if labelled:
        logger.info(f"Backfilled jobs.work_type on {labelled} rows")
    return labelled
