"""
Company management routes with input validation.

Security features:
- Input length limits to prevent DoS attacks
- URL validation for website field
- Sanitized text inputs
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_, func
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime
import re

from database import get_db
from models import Company, Job, User
from middleware.auth import get_current_user, is_admin
from services.company_resolver import registry_company_keys, normalize_company_key

router = APIRouter(prefix="/api/companies", tags=["companies"])

# Valid company sizes
VALID_COMPANY_SIZES = {"1-10", "11-50", "51-200", "201-500", "501-1000", "1001-5000", "5001-10000", "10000+"}


class CompanyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Company name")
    website: Optional[str] = Field(None, max_length=500)
    industry: Optional[str] = Field(None, max_length=100)
    size: Optional[str] = Field(None, max_length=50)
    location: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=5000)

    @field_validator('website')
    @classmethod
    def validate_website(cls, v):
        if v:
            if not re.match(r'^https?://', v):
                raise ValueError("Website must start with http:// or https://")
        return v


class CompanyUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    website: Optional[str] = Field(None, max_length=500)
    industry: Optional[str] = Field(None, max_length=100)
    size: Optional[str] = Field(None, max_length=50)
    location: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = Field(None, max_length=5000)

    @field_validator('website')
    @classmethod
    def validate_website(cls, v):
        if v:
            if not re.match(r'^https?://', v):
                raise ValueError("Website must start with http:// or https://")
        return v


class CompanyResponse(BaseModel):
    id: int
    name: str
    website: Optional[str]
    industry: Optional[str]
    size: Optional[str]
    location: Optional[str]
    notes: Optional[str]
    created_at: Optional[datetime]
    job_count: int = 0

    class Config:
        from_attributes = True


@router.get("")
def get_all_companies(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    companies = db.query(Company).filter(
        or_(Company.user_id == current_user.id, Company.user_id == None)
    ).all()

    # One grouped count of jobs visible to this user (shared + own), instead of
    # loading every job of every company.
    job_counts = dict(
        db.query(Job.company_id, func.count(Job.id)).filter(
            Job.company_id.isnot(None),
            or_(Job.user_id == None, Job.user_id == current_user.id),
        ).group_by(Job.company_id).all()
    )

    # has_scraper: a registry scraper covers this company ("tracked"); False for
    # one-off employers that arrived via aggregator feeds / ATS sources.
    scraper_keys = registry_company_keys()

    result = []
    for company in companies:
        result.append({
            "has_scraper": company.user_id is None and normalize_company_key(company.name) in scraper_keys,
            "id": company.id,
            "name": company.name,
            "website": company.website,
            "industry": company.industry,
            "size": company.size,
            "location": company.location,
            "notes": company.notes,
            "created_at": company.created_at,
            "job_count": job_counts.get(company.id, 0)
        })
    return result


@router.get("/{company_id}")
def get_company(
    company_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    company = db.query(Company).filter(
        Company.id == company_id,
        or_(Company.user_id == current_user.id, Company.user_id == None)
    ).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")

    # Only show jobs visible to this user
    user_jobs = [j for j in company.jobs if j.user_id == current_user.id or j.user_id is None]
    return {
        "id": company.id,
        "name": company.name,
        "website": company.website,
        "industry": company.industry,
        "size": company.size,
        "location": company.location,
        "notes": company.notes,
        "created_at": company.created_at,
        "job_count": len(user_jobs),
        "jobs": [{"id": j.id, "title": j.title, "status": j.status} for j in user_jobs]
    }


@router.post("")
def create_company(
    company: CompanyCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_company = Company(**company.model_dump(), user_id=current_user.id)
    db.add(db_company)
    db.commit()
    db.refresh(db_company)
    return {"id": db_company.id, "message": "Company created successfully"}


def _editable_company(db: Session, company_id: int, user: User) -> Company:
    """
    Admins may edit/delete any company; other users only their own.
    Shared rows (user_id NULL) are admin-only (403), others' rows are 404.
    """
    company = db.query(Company).filter(Company.id == company_id).first()
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    if is_admin(user) or company.user_id == user.id:
        return company
    if company.user_id is None:
        raise HTTPException(status_code=403, detail="Only admins can modify shared companies")
    raise HTTPException(status_code=404, detail="Company not found")


@router.put("/{company_id}")
def update_company(
    company_id: int,
    company: CompanyUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_company = _editable_company(db, company_id, current_user)

    update_data = company.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_company, key, value)

    db.commit()
    db.refresh(db_company)
    return {"message": "Company updated successfully"}


@router.delete("/{company_id}")
def delete_company(
    company_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_company = _editable_company(db, company_id, current_user)

    job_count = db.query(func.count(Job.id)).filter(Job.company_id == db_company.id).scalar() or 0
    if job_count:
        raise HTTPException(
            status_code=409,
            detail=f"Company has {job_count} jobs; delete or move them first "
                   "(duplicates: run scripts/merge_duplicate_companies.py)",
        )

    from models import Contact, IngestionSource
    db.query(Contact).filter(Contact.company_id == db_company.id).update(
        {"company_id": None}, synchronize_session=False
    )
    db.query(IngestionSource).filter(IngestionSource.company_id == db_company.id).update(
        {"company_id": None}, synchronize_session=False
    )
    db.delete(db_company)
    db.commit()
    return {"message": "Company deleted successfully"}
