"""
Database configuration for JobTrails.

Supports both SQLite (development) and PostgreSQL (production).
"""

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import QueuePool, StaticPool
from contextlib import contextmanager
import os
import sys

# Handle imports whether running from backend/ or project root
try:
    from config import settings
except ImportError:
    from config import settings


def get_engine():
    """
    Create SQLAlchemy engine with appropriate settings for the database type.
    """
    if settings.is_sqlite:
        # SQLite configuration
        return create_engine(
            settings.database_url,
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
    else:
        # PostgreSQL configuration with connection pooling
        return create_engine(
            settings.database_url,
            poolclass=QueuePool,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_recycle=settings.db_pool_recycle,
            pool_pre_ping=True,  # Verify connections before use
        )


# Create engine with error handling
try:
    engine = get_engine()
    print(f"Database engine created: {settings.database_url.split('@')[-1] if '@' in settings.database_url else 'local'}")
except Exception as e:
    print(f"WARNING: Failed to create database engine: {e}")
    # Create a minimal engine that will fail gracefully on first use
    engine = None


def _run_early_migrations():
    """Run critical migrations before models are loaded."""
    if engine is None:
        print("Skipping early migrations - no database connection")
        return

    from sqlalchemy import text

    new_columns = [
        ("full_name", "VARCHAR(255)"),
        ("job_title", "VARCHAR(255)"),
        ("date_of_birth", "DATE"),
        ("resume_email", "VARCHAR(255)"),
        ("language", "VARCHAR(10) DEFAULT 'en'"),
        ("base_resume_id", "INTEGER"),
        ("ai_model", "VARCHAR(50) DEFAULT 'gpt-4'"),
        ("employment_status", "VARCHAR(50)"),
        ("job_titles", "JSON"),
        ("experience_level", "VARCHAR(50)"),
        ("industry", "VARCHAR(100)"),
        ("work_type", "VARCHAR(50)"),
        ("available_date", "DATE"),
        ("preferred_cities", "JSON"),
        ("remote_ok", "BOOLEAN DEFAULT FALSE"),
        ("hybrid_ok", "BOOLEAN DEFAULT FALSE"),
        ("drivers_license", "VARCHAR(10)"),
        ("security_clearance", "VARCHAR(10)"),
        ("apply_mode", "VARCHAR(20) DEFAULT 'hybrid'"),
        ("excluded_companies", "JSON"),
        ("onboarding_completed", "BOOLEAN DEFAULT FALSE"),
        ("onboarding_completed_at", "TIMESTAMP"),
    ]

    try:
        with engine.connect() as conn:
            # Check if users table exists
            result = conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'users')"
            ))
            if not result.scalar():
                return  # Users table doesn't exist yet

            # Get existing columns
            result = conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name = 'users'"
            ))
            existing = {row[0] for row in result}

            # Add missing columns
            for col_name, col_type in new_columns:
                if col_name not in existing:
                    try:
                        conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_type}"))
                        print(f"Added column: {col_name}")
                    except Exception as e:
                        print(f"Could not add {col_name}: {e}")

            conn.commit()

            # One-time migration: Set onboarding_completed for users with resumes
            try:
                result = conn.execute(text("""
                    UPDATE users SET onboarding_completed = true
                    WHERE onboarding_completed IS NOT TRUE
                    AND id IN (SELECT DISTINCT user_id FROM user_documents WHERE document_type = 'resume')
                """))
                if result.rowcount > 0:
                    print(f"Marked {result.rowcount} users with resumes as onboarding completed")
                conn.commit()
            except Exception as e:
                print(f"Onboarding migration note: {e}")

    except Exception as e:
        print(f"Early migration error: {e}")


# Run migrations before models load
_run_early_migrations()

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency for FastAPI routes to get database session.

    Usage:
        @app.get("/items")
        def get_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """
    Context manager for database sessions outside of FastAPI routes.

    Usage:
        with get_db_context() as db:
            items = db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def create_tables():
    """
    Create all tables defined in models.

    Note: In production, use Alembic migrations instead.
    """
    try:
        from models import (
            Job, Company, Contact, Interview, Note, Document,
            IngestionSource, RoleProfile, User, JobRelevanceScore,
            ScraperRun, ScraperConfigDB, UserDocument
        )
    except ImportError:
        from models import (
            Job, Company, Contact, Interview, Note, Document,
            IngestionSource, RoleProfile, User, JobRelevanceScore,
            ScraperRun, ScraperConfigDB, UserDocument
        )
    Base.metadata.create_all(bind=engine)


def drop_tables():
    """
    Drop all tables. Use with caution!
    """
    Base.metadata.drop_all(bind=engine)


def get_database_info() -> dict:
    """
    Get information about the current database connection.
    """
    return {
        "url": settings.database_url.split("@")[-1] if "@" in settings.database_url else settings.database_url,
        "type": "postgresql" if settings.is_postgres else "sqlite",
        "pool_size": settings.db_pool_size if settings.is_postgres else "N/A",
        "max_overflow": settings.db_max_overflow if settings.is_postgres else "N/A",
    }
