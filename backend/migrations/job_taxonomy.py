"""
Add jobs.role_category / jobs.seniority and companies.domain, and backfill them (idempotent).

New and edited rows get them from the save hooks in models.py; this fills rows saved before the
columns existed, and companies added to data/company_domains.json since. Called from
main.run_migrations under the startup advisory lock, in the background migration thread.
"""
import logging
from collections import defaultdict

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

BATCH = 1000


def _add_column(connection, table: str, column: str, ddl: str, postgres: bool) -> None:
    if column in {c["name"] for c in inspect(connection).get_columns(table)}:
        return
    connection.execute(text(
        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}" if postgres
        else f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    logger.info(f"Added {table}.{column}")


def migrate_job_taxonomy(connection, max_rows: int = 500_000, commit_batches: bool = False) -> int:
    """Add the columns + indexes, then label rows still NULL. Returns job rows labelled."""
    insp = inspect(connection)
    if not insp.has_table("jobs") or not insp.has_table("companies"):
        return 0
    postgres = connection.dialect.name == "postgresql"
    _add_column(connection, "jobs", "role_category", "VARCHAR(32)", postgres)
    _add_column(connection, "jobs", "seniority", "VARCHAR(16)", postgres)
    _add_column(connection, "companies", "domain", "VARCHAR(40)", postgres)
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_role_category ON jobs(role_category)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_jobs_seniority ON jobs(seniority)"))
    connection.execute(text("CREATE INDEX IF NOT EXISTS ix_companies_domain ON companies(domain)"))
    if commit_batches:
        connection.commit()
    backfill_company_domains(connection)
    if commit_batches:
        connection.commit()
    return backfill_job_taxonomy(connection, max_rows=max_rows, commit_batches=commit_batches)


def backfill_company_domains(connection) -> int:
    """Set companies.domain where it is NULL and the company is in data/company_domains.json."""
    from services.job_taxonomy import company_domain

    by_domain: dict[str, list[int]] = defaultdict(list)
    for cid, name in connection.execute(text("SELECT id, name FROM companies WHERE domain IS NULL")).fetchall():
        d = company_domain(name)
        if d:
            by_domain[d].append(cid)
    for d, ids in by_domain.items():
        connection.execute(
            text(f"UPDATE companies SET domain = :d WHERE id IN ({','.join(str(int(i)) for i in ids)})"), {"d": d})
    n = sum(len(v) for v in by_domain.values())
    if n:
        logger.info(f"Backfilled companies.domain on {n} rows")
    return n


def backfill_job_taxonomy(connection, max_rows: int = 500_000, commit_batches: bool = False) -> int:
    """Label jobs whose role_category or seniority is NULL, in id batches."""
    from services.job_taxonomy import role_category, seniority

    labelled, last_id = 0, 0
    while labelled < max_rows:
        rows = connection.execute(text(
            "SELECT id, title, department FROM jobs "
            "WHERE (role_category IS NULL OR seniority IS NULL) AND id > :last ORDER BY id LIMIT :batch"
        ), {"last": last_id, "batch": BATCH}).fetchall()
        if not rows:
            break
        groups: dict[tuple[str, str], list[int]] = defaultdict(list)
        for job_id, title, department in rows:
            groups[(role_category(title, department), seniority(title))].append(job_id)
        for (cat, lvl), ids in groups.items():
            connection.execute(
                text(f"UPDATE jobs SET role_category = :c, seniority = :s WHERE id IN ({','.join(str(int(i)) for i in ids)})"),
                {"c": cat, "s": lvl})
        labelled += len(rows)
        last_id = rows[-1][0]
        if commit_batches:  # short transactions: scrapers update these rows too
            connection.commit()
    if labelled:
        logger.info(f"Backfilled jobs.role_category / seniority on {labelled} rows")
    return labelled
