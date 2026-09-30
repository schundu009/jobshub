"""
Add employment_type + freshness columns to jobs (idempotent).

Called from main.run_migrations, which already runs under the startup
advisory lock, so only one worker/replica executes this DDL.
"""
import logging

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

# column -> (PostgreSQL DDL type, SQLite DDL type)
JOB_CLASSIFICATION_COLUMNS = [
    ("employment_type", "VARCHAR(20)", "VARCHAR(20)"),
    ("first_seen_at", "TIMESTAMP", "DATETIME"),
    ("last_seen_at", "TIMESTAMP", "DATETIME"),
    ("reposted_count", "INTEGER DEFAULT 0", "INTEGER DEFAULT 0"),
    ("is_evergreen", "BOOLEAN DEFAULT FALSE", "BOOLEAN DEFAULT 0"),
    ("evergreen_reason", "VARCHAR(40)", "VARCHAR(40)"),
    ("effective_posted_at", "TIMESTAMP", "DATETIME"),
    ("country_codes", "VARCHAR(200)", "VARCHAR(200)"),
]

JOB_CLASSIFICATION_INDEXES = [
    ("ix_jobs_employment_type", "jobs(employment_type)"),
    ("ix_jobs_active_effective_posted", "jobs(is_active, effective_posted_at)"),
    ("ix_jobs_country_codes", "jobs(country_codes)"),
]


def migrate_job_classification(connection) -> list[str]:
    """Add missing columns + indexes and seed first_seen_at. Returns the columns added."""
    if not inspect(connection).has_table("jobs"):
        return []
    postgres = connection.dialect.name == "postgresql"
    existing = {c["name"] for c in inspect(connection).get_columns("jobs")}
    added = []
    for name, pg_type, sqlite_type in JOB_CLASSIFICATION_COLUMNS:
        if name in existing:
            continue
        if postgres:
            connection.execute(text(f"ALTER TABLE jobs ADD COLUMN IF NOT EXISTS {name} {pg_type}"))
        else:
            connection.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {sqlite_type}"))
        added.append(name)
    for idx_name, idx_cols in JOB_CLASSIFICATION_INDEXES:
        connection.execute(text(f"CREATE INDEX IF NOT EXISTS {idx_name} ON {idx_cols}"))
    # Our first sighting of pre-existing rows: when we stored them.
    connection.execute(text(
        "UPDATE jobs SET first_seen_at = COALESCE(created_at, date_found) "
        "WHERE first_seen_at IS NULL AND (created_at IS NOT NULL OR date_found IS NOT NULL)"
    ))
    connection.execute(text(
        "UPDATE jobs SET effective_posted_at = CASE "
        "WHEN posted_date IS NOT NULL AND (first_seen_at IS NULL OR posted_date < first_seen_at) THEN posted_date "
        "ELSE first_seen_at END "
        "WHERE effective_posted_at IS NULL AND (posted_date IS NOT NULL OR first_seen_at IS NOT NULL)"
    ))
    connection.execute(text("UPDATE jobs SET reposted_count = 0 WHERE reposted_count IS NULL"))
    connection.execute(text("UPDATE jobs SET is_evergreen = FALSE WHERE is_evergreen IS NULL"))
    if postgres:
        _trigram_indexes(connection)
    added += _migrate_user_country_code(connection, postgres)
    if added:
        logger.info(f"Added columns: {', '.join(added)}")
    return added


def _migrate_user_country_code(connection, postgres: bool) -> list[str]:
    """users.country_code = ISO-2 of the free-text users.country (kept as is)."""
    if not inspect(connection).has_table("users"):
        return []
    cols = {c["name"] for c in inspect(connection).get_columns("users")}
    added = []
    if "country_code" not in cols:
        connection.execute(text(
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS country_code VARCHAR(2)" if postgres
            else "ALTER TABLE users ADD COLUMN country_code VARCHAR(2)"))
        added.append("users.country_code")
    if "country" in cols:
        from services.job_location import normalize_country
        rows = connection.execute(text(
            "SELECT id, country FROM users WHERE country_code IS NULL AND country IS NOT NULL AND country <> ''"
        )).fetchall()
        for uid, country in rows:
            code = normalize_country(country)
            if code:
                connection.execute(text("UPDATE users SET country_code = :c WHERE id = :i"), {"c": code, "i": uid})
    return added


def _trigram_indexes(connection) -> None:
    """country_codes is matched with LIKE '%,US,%': a trigram GIN index serves that on PostgreSQL."""
    for table in ("jobs", "contract_jobs"):
        if not inspect(connection).has_table(table):
            continue
        try:
            with connection.begin_nested():
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
                connection.execute(text(
                    f"CREATE INDEX IF NOT EXISTS ix_{table}_country_codes_trgm "
                    f"ON {table} USING gin (country_codes gin_trgm_ops)"))
        except Exception as e:  # no permission for the extension: the btree index still helps equality/NULL checks
            logger.info(f"trigram index on {table}.country_codes skipped: {e}")
