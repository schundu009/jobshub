#!/usr/bin/env python3
"""
Migration script to add new columns to ingestion_sources table.

Run from backend directory:
    python scripts/migrate_ingestion_sources.py
"""

import sqlite3
import os
from datetime import datetime

# Path to database
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
DB_PATH = os.path.join(DATA_DIR, "jobtrails.db")


def get_existing_columns(cursor, table_name):
    """Get list of existing column names in a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    return [row[1] for row in cursor.fetchall()]


def migrate():
    """Add new columns to ingestion_sources table if they don't exist."""

    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        print("Please run the application first to create the database.")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Check if table exists
        cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='ingestion_sources'
        """)

        if not cursor.fetchone():
            print("Table 'ingestion_sources' does not exist.")
            print("It will be created when the application starts.")
            return True

        # Get existing columns
        existing_columns = get_existing_columns(cursor, "ingestion_sources")
        print(f"Existing columns: {existing_columns}")

        # Define new columns to add
        new_columns = [
            ("company_name", "VARCHAR(255)"),
            ("first_seen_at", "DATETIME DEFAULT CURRENT_TIMESTAMP"),
            ("last_checked_at", "DATETIME"),
            ("last_successful_at", "DATETIME"),
            ("job_count", "INTEGER DEFAULT 0"),
            ("error_message", "VARCHAR(500)"),
        ]

        added = []
        skipped = []

        for col_name, col_type in new_columns:
            if col_name in existing_columns:
                skipped.append(col_name)
            else:
                try:
                    cursor.execute(f"ALTER TABLE ingestion_sources ADD COLUMN {col_name} {col_type}")
                    added.append(col_name)
                    print(f"  Added column: {col_name}")
                except sqlite3.OperationalError as e:
                    print(f"  Error adding {col_name}: {e}")

        conn.commit()

        print("\n--- Migration Summary ---")
        if added:
            print(f"Added columns: {', '.join(added)}")
        if skipped:
            print(f"Skipped (already exist): {', '.join(skipped)}")

        # Show final table structure
        print("\n--- Final Table Structure ---")
        cursor.execute("PRAGMA table_info(ingestion_sources)")
        for row in cursor.fetchall():
            print(f"  {row[1]}: {row[2]} {'NOT NULL' if row[3] else ''} {'DEFAULT ' + str(row[4]) if row[4] else ''}")

        return True

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


if __name__ == "__main__":
    print("=== Ingestion Sources Migration ===\n")
    success = migrate()
    print("\n" + ("Migration completed successfully!" if success else "Migration failed!"))
