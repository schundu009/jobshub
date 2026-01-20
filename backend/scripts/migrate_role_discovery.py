#!/usr/bin/env python3
"""
Migration script to create tables for role-aware job discovery.

Creates:
- role_profiles: Role definitions with relevance criteria
- users: User accounts with role assignments
- job_relevance_scores: Cached relevance scores (optional optimization)

Run from backend directory:
    python scripts/migrate_role_discovery.py
"""

import sqlite3
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Path to database
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(os.path.dirname(BASE_DIR), "data")
DB_PATH = os.path.join(DATA_DIR, "jobtrails.db")


def table_exists(cursor, table_name):
    """Check if a table exists in the database."""
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name=?
    """, (table_name,))
    return cursor.fetchone() is not None


def migrate():
    """Create new tables for role-aware job discovery."""

    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        print("Please run the application first to create the database.")
        return False

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Create role_profiles table
        if not table_exists(cursor, "role_profiles"):
            print("Creating role_profiles table...")
            cursor.execute("""
                CREATE TABLE role_profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug VARCHAR(50) UNIQUE NOT NULL,
                    name VARCHAR(100) NOT NULL,
                    description TEXT,
                    title_patterns JSON NOT NULL DEFAULT '{}',
                    positive_keywords JSON NOT NULL DEFAULT '{}',
                    negative_keywords JSON NOT NULL DEFAULT '[]',
                    seniority_config JSON DEFAULT '{}',
                    relevance_threshold REAL DEFAULT 30.0,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX idx_role_profiles_slug ON role_profiles(slug)")
            print("  Created role_profiles table")
        else:
            print("  role_profiles table already exists")

        # 2. Create users table
        if not table_exists(cursor, "users"):
            print("Creating users table...")
            cursor.execute("""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email VARCHAR(255) UNIQUE NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    role_profile_id INTEGER REFERENCES role_profiles(id),
                    custom_preferences JSON DEFAULT '{}',
                    preferred_locations JSON DEFAULT '[]',
                    target_seniority VARCHAR(50),
                    min_salary INTEGER,
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX idx_users_email ON users(email)")
            print("  Created users table")

            # Create default user
            cursor.execute("""
                INSERT INTO users (id, email, name)
                VALUES (1, 'user@example.com', 'Default User')
            """)
            print("  Created default user (id=1)")
        else:
            print("  users table already exists")

        # 3. Create job_relevance_scores table (optional caching)
        if not table_exists(cursor, "job_relevance_scores"):
            print("Creating job_relevance_scores table...")
            cursor.execute("""
                CREATE TABLE job_relevance_scores (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    relevance_score REAL NOT NULL,
                    is_relevant BOOLEAN NOT NULL,
                    score_breakdown JSON,
                    computed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    role_profile_id INTEGER,
                    UNIQUE(job_id, user_id)
                )
            """)
            cursor.execute("CREATE INDEX idx_relevance_job_id ON job_relevance_scores(job_id)")
            cursor.execute("CREATE INDEX idx_relevance_user_id ON job_relevance_scores(user_id)")
            cursor.execute("CREATE INDEX idx_relevance_score ON job_relevance_scores(relevance_score)")
            cursor.execute("CREATE INDEX idx_relevance_is_relevant ON job_relevance_scores(is_relevant)")
            print("  Created job_relevance_scores table")
        else:
            print("  job_relevance_scores table already exists")

        conn.commit()
        return True

    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


def seed_role_profiles():
    """Seed the role_profiles table with built-in profiles."""
    from services.role_profiles_data import get_all_profiles
    import json

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        profiles = get_all_profiles()
        created = 0
        skipped = 0

        for profile in profiles:
            # Check if exists
            cursor.execute("SELECT id FROM role_profiles WHERE slug = ?", (profile["slug"],))
            if cursor.fetchone():
                skipped += 1
                continue

            cursor.execute("""
                INSERT INTO role_profiles (
                    slug, name, description, title_patterns,
                    positive_keywords, negative_keywords,
                    seniority_config, relevance_threshold
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                profile["slug"],
                profile["name"],
                profile["description"],
                json.dumps(profile["title_patterns"]),
                json.dumps(profile["positive_keywords"]),
                json.dumps(profile["negative_keywords"]),
                json.dumps(profile.get("seniority_config", {})),
                profile.get("relevance_threshold", 30.0)
            ))
            created += 1

        conn.commit()
        print(f"\nSeeded role profiles: {created} created, {skipped} skipped")
        return True

    except Exception as e:
        print(f"Seeding failed: {e}")
        conn.rollback()
        return False

    finally:
        conn.close()


def show_tables():
    """Show current table structure."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    print("\n--- Current Tables ---")
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    for row in cursor.fetchall():
        print(f"  {row[0]}")

    for table in ["role_profiles", "users", "job_relevance_scores"]:
        if table_exists(cursor, table):
            print(f"\n--- {table} columns ---")
            cursor.execute(f"PRAGMA table_info({table})")
            for row in cursor.fetchall():
                print(f"  {row[1]}: {row[2]}")

    conn.close()


if __name__ == "__main__":
    print("=" * 60)
    print("ROLE-AWARE JOB DISCOVERY MIGRATION")
    print("=" * 60)

    print("\n1. Creating tables...")
    if migrate():
        print("\nTables created successfully!")

        print("\n2. Seeding role profiles...")
        seed_role_profiles()

        show_tables()

        print("\n" + "=" * 60)
        print("Migration completed successfully!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Restart the backend server")
        print("2. Call POST /api/users/roles/seed to verify profiles")
        print("3. Set your role: PATCH /api/users/1/role?role_slug=devops")
        print("4. Browse jobs: GET /api/jobs?role=devops")
    else:
        print("\nMigration failed!")
