#!/usr/bin/env python3
"""Add posted_date and department columns to jobs table."""
import sys
sys.path.insert(0, '/Users/chundu/jobportal/backend')

from database import engine
from sqlalchemy import text

def run_migration():
    with engine.connect() as conn:
        # Add posted_date column
        try:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN posted_date TIMESTAMP"))
            print("Added posted_date column")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print("posted_date column already exists")
            else:
                print(f"Error adding posted_date: {e}")

        # Add department column
        try:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN department VARCHAR(255)"))
            print("Added department column")
        except Exception as e:
            if "duplicate column" in str(e).lower():
                print("department column already exists")
            else:
                print(f"Error adding department: {e}")

        conn.commit()
        print("Migration complete!")

if __name__ == "__main__":
    run_migration()
