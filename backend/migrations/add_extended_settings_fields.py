"""
Migration: Add extended user settings fields

Adds new columns to the users table for comprehensive settings:
- Extended profile (full_name, job_title, date_of_birth)
- Preferences (resume_email, language, base_resume_id, ai_model)
- Auto Apply settings (employment_status, job_titles, experience_level, etc.)
"""

import sqlite3
import os
import sys

# Get database path
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "jobtrails.db")


def run_migration():
    """Run the migration to add extended settings fields."""
    print(f"Running migration on: {DB_PATH}")

    if not os.path.exists(DB_PATH):
        print("Database not found. Skipping migration.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Get existing columns in users table
    cursor.execute("PRAGMA table_info(users)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    print(f"Existing columns in users: {len(existing_columns)}")

    # New columns to add to users table
    new_columns = [
        # Extended profile
        ("full_name", "VARCHAR(255)"),
        ("job_title", "VARCHAR(255)"),
        ("date_of_birth", "DATE"),

        # Preferences
        ("resume_email", "VARCHAR(255)"),
        ("language", "VARCHAR(10) DEFAULT 'en'"),
        ("base_resume_id", "INTEGER"),
        ("ai_model", "VARCHAR(50) DEFAULT 'gpt-4'"),

        # Auto Apply settings
        ("employment_status", "VARCHAR(50)"),
        ("job_titles", "TEXT"),  # JSON array
        ("experience_level", "VARCHAR(50)"),
        ("industry", "VARCHAR(100)"),
        ("work_type", "VARCHAR(50)"),
        ("available_date", "DATE"),
        ("preferred_cities", "TEXT"),  # JSON array
        ("remote_ok", "BOOLEAN DEFAULT 0"),
        ("hybrid_ok", "BOOLEAN DEFAULT 0"),
        ("drivers_license", "VARCHAR(10)"),
        ("security_clearance", "VARCHAR(10)"),
        ("apply_mode", "VARCHAR(20) DEFAULT 'hybrid'"),
        ("excluded_companies", "TEXT"),  # JSON array
    ]

    # Add new columns to users table
    added = 0
    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}")
                print(f"  Added column: {col_name}")
                added += 1
            except sqlite3.OperationalError as e:
                if "duplicate column name" in str(e).lower():
                    print(f"  Column {col_name} already exists")
                else:
                    print(f"  Error adding {col_name}: {e}")
        else:
            print(f"  Column {col_name} already exists")

    print(f"\nAdded {added} new columns to users table")

    conn.commit()
    conn.close()

    print("\nMigration completed successfully!")


if __name__ == "__main__":
    run_migration()
