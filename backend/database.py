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


# Create engine
engine = get_engine()

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
            ScraperRun, ScraperConfigDB
        )
    except ImportError:
        from models import (
            Job, Company, Contact, Interview, Note, Document,
            IngestionSource, RoleProfile, User, JobRelevanceScore,
            ScraperRun, ScraperConfigDB
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
