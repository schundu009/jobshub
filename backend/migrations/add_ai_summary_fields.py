#!/usr/bin/env python3
"""Add ai_summary and ai_tech_stack columns to jobs table."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import engine
from sqlalchemy import text

def run_migration():
    with engine.connect() as conn:
        # Add ai_summary column
        try:
            conn.execute(text("ALTER TABLE jobs ADD COLUMN ai_summary TEXT"))
            print("Added ai_summary column")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("ai_summary column already exists")
            else:
                print(f"Error adding ai_summary: {e}")

        # Add ai_tech_stack column (JSON type for PostgreSQL, TEXT for SQLite)
        try:
            # Try JSONB first (PostgreSQL)
            conn.execute(text("ALTER TABLE jobs ADD COLUMN ai_tech_stack JSONB"))
            print("Added ai_tech_stack column (JSONB)")
        except Exception as e:
            if "duplicate column" in str(e).lower() or "already exists" in str(e).lower():
                print("ai_tech_stack column already exists")
            else:
                # Fall back to TEXT for SQLite
                try:
                    conn.execute(text("ALTER TABLE jobs ADD COLUMN ai_tech_stack TEXT"))
                    print("Added ai_tech_stack column (TEXT)")
                except Exception as e2:
                    if "duplicate column" in str(e2).lower() or "already exists" in str(e2).lower():
                        print("ai_tech_stack column already exists")
                    else:
                        print(f"Error adding ai_tech_stack: {e2}")

        conn.commit()
        print("Migration complete!")

if __name__ == "__main__":
    run_migration()
