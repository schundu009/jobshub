"""
cariara.com identity link columns on users (idempotent).

Called from database._run_early_migrations_locked (under the early-migration
advisory lock) because the ORM selects these columns on every User query, so
they must exist before the app serves requests.
"""
import logging

from sqlalchemy import inspect, text

logger = logging.getLogger(__name__)

# column -> (PostgreSQL DDL type, SQLite DDL type); all nullable.
CARIARA_USER_COLUMNS = [
    ("cariara_user_id", "VARCHAR(64)", "VARCHAR(64)"),
    ("identity_source", "VARCHAR(20)", "VARCHAR(20)"),
    ("cariara_plan", "VARCHAR(32)", "VARCHAR(32)"),
    ("cariara_plan_checked_at", "TIMESTAMP", "DATETIME"),
]

# Same name Base.metadata.create_all gives Column(unique=True, index=True).
CARIARA_USER_ID_INDEX = "ix_users_cariara_user_id"


def migrate_cariara_identity(connection) -> list[str]:
    """Add missing columns + the unique index. Returns the columns added."""
    if not inspect(connection).has_table("users"):
        return []
    postgres = connection.dialect.name == "postgresql"
    existing = {c["name"] for c in inspect(connection).get_columns("users")}
    added = []
    for name, pg_type, sqlite_type in CARIARA_USER_COLUMNS:
        if name in existing:
            continue
        if postgres:
            connection.execute(text(f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {name} {pg_type}"))
        else:
            connection.execute(text(f"ALTER TABLE users ADD COLUMN {name} {sqlite_type}"))
        added.append(name)
    # Unique allows many NULLs on both PostgreSQL and SQLite.
    connection.execute(text(
        f"CREATE UNIQUE INDEX IF NOT EXISTS {CARIARA_USER_ID_INDEX} ON users(cariara_user_id)"
    ))
    if added:
        logger.info("Added cariara identity columns to users: %s", ", ".join(added))
    return added
