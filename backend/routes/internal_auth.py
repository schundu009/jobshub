"""
Internal admin authentication - completely separate from user auth.

This provides a separate authentication system for internal admin access.
Admin credentials are stored in a separate table and are not shared with user accounts.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy.orm import Session
from sqlalchemy import Column, Integer, String, DateTime, Boolean
from datetime import datetime
import secrets
import hashlib
import os

from database import get_db, Base

router = APIRouter(prefix="/api/internal", tags=["internal"])

security = HTTPBasic()


# Admin user model - completely separate from User model
class AdminUser(Base):
    """Internal admin users - separate from regular users."""
    __tablename__ = "admin_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name = Column(String(255))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime)


def hash_password(password: str) -> str:
    """Hash password with salt."""
    salt = os.environ.get("ADMIN_SALT", "cariara-internal-salt")
    return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()


def verify_admin(credentials: HTTPBasicCredentials = Depends(security), db: Session = Depends(get_db)):
    """Verify admin credentials using HTTP Basic Auth."""
    admin = db.query(AdminUser).filter(
        AdminUser.username == credentials.username,
        AdminUser.is_active == True
    ).first()

    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    password_hash = hash_password(credentials.password)
    if not secrets.compare_digest(admin.password_hash, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )

    # Update last login
    admin.last_login = datetime.utcnow()
    db.commit()

    return admin


@router.get("/verify")
def verify_admin_access(admin: AdminUser = Depends(verify_admin)):
    """Verify admin credentials - returns admin info if valid."""
    return {
        "authenticated": True,
        "username": admin.username,
        "name": admin.name
    }


@router.get("/dashboard/stats")
def get_admin_stats(admin: AdminUser = Depends(verify_admin), db: Session = Depends(get_db)):
    """Get admin dashboard statistics."""
    from models import Job, Company, User, IngestionSource

    total_jobs = db.query(Job).count()
    total_companies = db.query(Company).count()
    total_users = db.query(User).count()
    total_sources = db.query(IngestionSource).count()

    # Jobs by status
    from sqlalchemy import func
    status_counts = dict(db.query(Job.status, func.count(Job.id)).group_by(Job.status).all())

    # Recent jobs
    recent_jobs = db.query(Job).order_by(Job.created_at.desc()).limit(10).all()

    return {
        "total_jobs": total_jobs,
        "total_companies": total_companies,
        "total_users": total_users,
        "total_sources": total_sources,
        "status_counts": status_counts,
        "recent_jobs": [
            {
                "id": job.id,
                "title": job.title,
                "company_name": job.company.name if job.company else None,
                "status": job.status,
                "created_at": job.created_at.isoformat() if job.created_at else None
            }
            for job in recent_jobs
        ]
    }


@router.get("/users")
def list_all_users(admin: AdminUser = Depends(verify_admin), db: Session = Depends(get_db)):
    """List all users in the system."""
    from models import User

    users = db.query(User).order_by(User.created_at.desc()).all()
    return [
        {
            "id": user.id,
            "email": user.email,
            "name": user.name,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None
        }
        for user in users
    ]


@router.get("/sources")
def list_ingestion_sources(admin: AdminUser = Depends(verify_admin), db: Session = Depends(get_db)):
    """List all ingestion sources."""
    from models import IngestionSource

    sources = db.query(IngestionSource).order_by(IngestionSource.created_at.desc()).all()
    return [
        {
            "id": source.id,
            "ats_type": source.ats_type,
            "company_slug": source.company_slug,
            "company_name": source.company_name,
            "is_active": source.is_active,
            "last_fetched": source.last_fetched.isoformat() if source.last_fetched else None,
            "job_count": source.job_count
        }
        for source in sources
    ]
