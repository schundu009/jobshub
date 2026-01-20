"""
Migration: Add user application settings fields

Adds new columns to the users table for job application data:
- Personal info (first_name, last_name, etc.)
- Address fields
- Work authorization fields
- Social profiles
- Professional summary

Also creates user_documents table for storing uploaded resumes and cover letters.
"""

import sqlite3
import os
import sys

# Get database path
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
DB_PATH = os.path.join(DATA_DIR, "jobtrails.db")


def run_migration():
    """Run the migration to add user settings fields."""
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
        # Personal info
        ("first_name", "VARCHAR(100)"),
        ("last_name", "VARCHAR(100)"),
        ("preferred_name", "VARCHAR(100)"),
        ("phone", "VARCHAR(50)"),
        ("country", "VARCHAR(50)"),
        # Address
        ("address_line1", "VARCHAR(255)"),
        ("address_line2", "VARCHAR(255)"),
        ("city", "VARCHAR(100)"),
        ("state", "VARCHAR(100)"),
        ("postal_code", "VARCHAR(20)"),
        ("address_country", "VARCHAR(50)"),
        # Work authorization
        ("us_authorized", "VARCHAR(20)"),
        ("requires_sponsorship", "VARCHAR(20)"),
        ("willing_to_relocate", "VARCHAR(20)"),
        ("us_government_employee", "VARCHAR(20)"),
        ("non_compete", "VARCHAR(20)"),
        ("work_arrangement", "VARCHAR(20)"),
        # Social profiles
        ("linkedin_url", "VARCHAR(500)"),
        ("github_url", "VARCHAR(500)"),
        ("portfolio_url", "VARCHAR(500)"),
        ("twitter_url", "VARCHAR(500)"),
        # Professional summary
        ("referral_source", "VARCHAR(50)"),
        ("bio", "TEXT"),
        ("skills", "TEXT"),
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

    # Create user_documents table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            document_type VARCHAR(50) NOT NULL,
            filename VARCHAR(255) NOT NULL,
            file_path VARCHAR(500) NOT NULL,
            file_size INTEGER,
            mime_type VARCHAR(100),
            is_default BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # Create index on user_id
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS ix_user_documents_user_id ON user_documents(user_id)
    """)

    print("Created user_documents table")

    conn.commit()
    conn.close()

    print("\nMigration completed successfully!")


if __name__ == "__main__":
    run_migration()
