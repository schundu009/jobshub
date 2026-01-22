#!/usr/bin/env python3
"""Add workday_email and workday_password_encrypted columns to auto_apply_configs table."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
from sqlalchemy import text

def run_migration():
    with engine.connect() as conn:
        # Add workday_email column
        try:
            conn.execute(text("ALTER TABLE auto_apply_configs ADD COLUMN workday_email VARCHAR(255)"))
            print("Added workday_email column")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("workday_email column already exists")
            else:
                print(f"Error adding workday_email: {e}")

        # Add workday_password_encrypted column
        try:
            conn.execute(text("ALTER TABLE auto_apply_configs ADD COLUMN workday_password_encrypted TEXT"))
            print("Added workday_password_encrypted column")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("workday_password_encrypted column already exists")
            else:
                print(f"Error adding workday_password_encrypted: {e}")

        conn.commit()
        print("Migration complete!")

if __name__ == "__main__":
    run_migration()
