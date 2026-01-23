#!/usr/bin/env python3
"""Extend job_url field to handle longer Eightfold URLs."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
from sqlalchemy import text

def run_migration():
    with engine.connect() as conn:
        # Extend job_url column to TEXT to handle very long URLs
        try:
            # PostgreSQL syntax to alter column type
            conn.execute(text("ALTER TABLE jobs ALTER COLUMN job_url TYPE TEXT"))
            print("Extended job_url column to TEXT")
        except Exception as e:
            if "already" in str(e).lower():
                print("job_url column already extended")
            else:
                print(f"Error extending job_url: {e}")

        # Also extend title to 500 chars for safety
        try:
            conn.execute(text("ALTER TABLE jobs ALTER COLUMN title TYPE VARCHAR(500)"))
            print("Extended title column to VARCHAR(500)")
        except Exception as e:
            print(f"Note: {e}")

        # Extend location to 500 chars
        try:
            conn.execute(text("ALTER TABLE jobs ALTER COLUMN location TYPE VARCHAR(500)"))
            print("Extended location column to VARCHAR(500)")
        except Exception as e:
            print(f"Note: {e}")

        conn.commit()
        print("Migration complete!")

if __name__ == "__main__":
    run_migration()
