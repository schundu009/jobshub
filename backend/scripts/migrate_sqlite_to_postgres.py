#!/usr/bin/env python3
"""
SQLite to PostgreSQL Data Migration Script.

This script migrates all data from the SQLite database to PostgreSQL.
Run this after setting up PostgreSQL and running Alembic migrations.

Usage:
    cd backend
    python scripts/migrate_sqlite_to_postgres.py
"""

import sqlite3
import os
import sys
from datetime import datetime

# Add parent directories to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.config import settings


# SQLite database path
SQLITE_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data",
    "jobtrails.db"
)


def get_sqlite_connection():
    """Get SQLite database connection."""
    if not os.path.exists(SQLITE_DB_PATH):
        raise FileNotFoundError(f"SQLite database not found at {SQLITE_DB_PATH}")
    return sqlite3.connect(SQLITE_DB_PATH)


def get_postgres_engine():
    """Get PostgreSQL engine."""
    return create_engine(settings.database_url)


def get_table_columns(sqlite_cursor, table_name):
    """Get column names for a table."""
    sqlite_cursor.execute(f"PRAGMA table_info({table_name})")
    return [col[1] for col in sqlite_cursor.fetchall()]


def get_postgres_columns(pg_session, table_name):
    """Get column names from PostgreSQL table."""
    result = pg_session.execute(text(f"""
        SELECT column_name
        FROM information_schema.columns
        WHERE table_name = '{table_name}'
        ORDER BY ordinal_position
    """))
    return [row[0] for row in result.fetchall()]


def get_common_columns(sqlite_cursor, pg_session, table_name):
    """Get columns that exist in both SQLite and PostgreSQL."""
    sqlite_cols = set(get_table_columns(sqlite_cursor, table_name))
    pg_cols = set(get_postgres_columns(pg_session, table_name))
    common = sqlite_cols & pg_cols

    # Preserve order from SQLite
    sqlite_ordered = get_table_columns(sqlite_cursor, table_name)
    return [col for col in sqlite_ordered if col in common]


def fetch_all_rows(sqlite_cursor, table_name, columns):
    """Fetch all rows from a SQLite table."""
    cols = ", ".join(columns)
    sqlite_cursor.execute(f"SELECT {cols} FROM {table_name}")
    return sqlite_cursor.fetchall()


# Boolean columns that need conversion from SQLite integers (0/1) to Python bool
BOOLEAN_COLUMNS = {
    "is_active", "is_enabled", "is_relevant", "success"
}


def convert_sqlite_value(col, val):
    """Convert SQLite value to PostgreSQL-compatible value."""
    if val is None:
        return None

    # Handle boolean columns (SQLite stores as 0/1)
    if col in BOOLEAN_COLUMNS:
        return bool(val) if val is not None else None

    # Handle datetime strings
    if col.endswith("_at") and isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    # Handle date columns
    if col.endswith("_date") or col in ("date_found", "date_applied", "posted_date"):
        if isinstance(val, str):
            try:
                return datetime.fromisoformat(val).date()
            except (ValueError, AttributeError):
                pass

    return val


def migrate_table(sqlite_cursor, pg_session, table_name, batch_size=1000):
    """
    Migrate a single table from SQLite to PostgreSQL.

    Returns the number of rows migrated.
    """
    # Get columns that exist in both databases
    columns = get_common_columns(sqlite_cursor, pg_session, table_name)
    all_sqlite_cols = get_table_columns(sqlite_cursor, table_name)

    # Log column differences
    pg_cols = set(get_postgres_columns(pg_session, table_name))
    sqlite_cols = set(all_sqlite_cols)
    if sqlite_cols != pg_cols:
        missing_in_pg = sqlite_cols - pg_cols
        missing_in_sqlite = pg_cols - sqlite_cols
        if missing_in_pg:
            print(f"    Note: Skipping columns not in PostgreSQL: {missing_in_pg}")
        if missing_in_sqlite:
            print(f"    Note: Columns only in PostgreSQL: {missing_in_sqlite}")

    rows = fetch_all_rows(sqlite_cursor, table_name, columns)

    if not rows:
        print(f"  {table_name}: 0 rows (empty)")
        return 0

    # Build INSERT statement
    cols_str = ", ".join(columns)
    placeholders = ", ".join([f":{col}" for col in columns])
    insert_sql = text(f"INSERT INTO {table_name} ({cols_str}) VALUES ({placeholders})")

    # Insert in batches
    total_rows = len(rows)
    migrated = 0

    for i in range(0, total_rows, batch_size):
        batch = rows[i:i + batch_size]

        for row in batch:
            # Convert row to dict with proper type conversions
            row_dict = {}
            for col, val in zip(columns, row):
                row_dict[col] = convert_sqlite_value(col, val)

            try:
                pg_session.execute(insert_sql, row_dict)
                migrated += 1
            except Exception as e:
                print(f"    Error inserting row in {table_name}: {e}")
                print(f"    Row data: {row_dict}")
                continue

        pg_session.commit()
        print(f"  {table_name}: {migrated}/{total_rows} rows migrated...")

    print(f"  {table_name}: {migrated} rows migrated (complete)")
    return migrated


def reset_sequences(pg_session, table_name):
    """Reset PostgreSQL sequence for a table's primary key."""
    try:
        # Get the max ID
        result = pg_session.execute(text(f"SELECT MAX(id) FROM {table_name}"))
        max_id = result.scalar()

        if max_id:
            # Reset the sequence
            seq_name = f"{table_name}_id_seq"
            pg_session.execute(
                text(f"SELECT setval('{seq_name}', :max_id, true)"),
                {"max_id": max_id}
            )
            pg_session.commit()
            print(f"  Reset sequence {seq_name} to {max_id}")
    except Exception as e:
        print(f"  Warning: Could not reset sequence for {table_name}: {e}")


def main():
    """Main migration function."""
    print("=" * 60)
    print("SQLite to PostgreSQL Migration")
    print("=" * 60)
    print(f"\nSource: {SQLITE_DB_PATH}")
    print(f"Target: {settings.database_url.split('@')[-1]}")
    print()

    # Confirm with user
    response = input("This will migrate data to PostgreSQL. Continue? [y/N]: ")
    if response.lower() != 'y':
        print("Migration cancelled.")
        return

    # Connect to databases
    print("\nConnecting to databases...")
    sqlite_conn = get_sqlite_connection()
    sqlite_cursor = sqlite_conn.cursor()

    pg_engine = get_postgres_engine()
    Session = sessionmaker(bind=pg_engine)
    pg_session = Session()

    # Tables in migration order (respecting foreign key dependencies)
    tables_to_migrate = [
        # Independent tables first
        "role_profiles",
        "companies",
        "scraper_configs",
        "scraper_runs",
        # Tables with single FK
        "users",  # FK: role_profiles
        "contacts",  # FK: companies
        "ingestion_sources",  # FK: companies
        "jobs",  # FK: companies
        # Tables with FK to jobs
        "interviews",  # FK: jobs
        "notes",  # FK: jobs
        "documents",  # FK: jobs
        # Junction/score tables
        "job_relevance_scores",  # FK: jobs, users
    ]

    print("\nMigrating tables...")
    print("-" * 40)

    total_migrated = 0

    for table in tables_to_migrate:
        try:
            # Check if table exists in SQLite
            sqlite_cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
                (table,)
            )
            if not sqlite_cursor.fetchone():
                print(f"  {table}: skipped (not in SQLite)")
                continue

            # Check if PostgreSQL table is empty
            result = pg_session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            pg_count = result.scalar()

            if pg_count > 0:
                print(f"  {table}: skipped ({pg_count} rows already exist in PostgreSQL)")
                continue

            # Migrate the table
            rows = migrate_table(sqlite_cursor, pg_session, table)
            total_migrated += rows

            # Reset sequence if rows were migrated
            if rows > 0:
                reset_sequences(pg_session, table)

        except Exception as e:
            print(f"  {table}: ERROR - {e}")
            pg_session.rollback()

    print("-" * 40)
    print(f"\nMigration complete! Total rows migrated: {total_migrated}")

    # Verification
    print("\nVerification - Row counts:")
    print("-" * 40)

    for table in tables_to_migrate:
        try:
            sqlite_cursor.execute(f"SELECT COUNT(*) FROM {table}")
            sqlite_count = sqlite_cursor.fetchone()[0]

            result = pg_session.execute(text(f"SELECT COUNT(*) FROM {table}"))
            pg_count = result.scalar()

            status = "OK" if sqlite_count == pg_count else "MISMATCH"
            print(f"  {table}: SQLite={sqlite_count}, PostgreSQL={pg_count} [{status}]")
        except Exception as e:
            print(f"  {table}: Error verifying - {e}")

    # Cleanup
    sqlite_conn.close()
    pg_session.close()

    print("\nDone!")


if __name__ == "__main__":
    main()
