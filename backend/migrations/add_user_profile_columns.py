"""
Migration to add missing user profile columns.
Run this to add new columns to the users table.
"""

import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
from sqlalchemy import text


def run_migration():
    """Add missing columns to users table."""

    # List of columns to add (column_name, column_definition)
    columns_to_add = [
        ("full_name", "VARCHAR(255)"),
        ("job_title", "VARCHAR(255)"),
        ("date_of_birth", "DATE"),
        ("resume_email", "VARCHAR(255)"),
        ("language", "VARCHAR(10) DEFAULT 'en'"),
        ("base_resume_id", "INTEGER REFERENCES user_documents(id)"),
        ("ai_model", "VARCHAR(50) DEFAULT 'gpt-4'"),
        ("employment_status", "VARCHAR(50)"),
        ("job_titles", "JSON DEFAULT '[]'"),
        ("experience_level", "VARCHAR(50)"),
        ("industry", "VARCHAR(100)"),
        ("work_type", "VARCHAR(50)"),
        ("available_date", "DATE"),
        ("preferred_cities", "JSON DEFAULT '[]'"),
        ("remote_ok", "BOOLEAN DEFAULT FALSE"),
        ("hybrid_ok", "BOOLEAN DEFAULT FALSE"),
        ("drivers_license", "VARCHAR(10)"),
        ("security_clearance", "VARCHAR(10)"),
        ("apply_mode", "VARCHAR(20) DEFAULT 'hybrid'"),
        ("excluded_companies", "JSON DEFAULT '[]'"),
    ]

    with engine.connect() as conn:
        for col_name, col_def in columns_to_add:
            try:
                # Check if column exists
                result = conn.execute(text(f"""
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'users' AND column_name = '{col_name}'
                """))

                if result.fetchone() is None:
                    # Column doesn't exist, add it
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                    conn.commit()
                    print(f"Added column: {col_name}")
                else:
                    print(f"Column already exists: {col_name}")

            except Exception as e:
                print(f"Error adding column {col_name}: {e}")
                conn.rollback()

    print("Migration complete!")


if __name__ == "__main__":
    run_migration()
