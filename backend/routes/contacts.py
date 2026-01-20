"""
Contact management routes with input validation.

Security features:
- Input length limits
- Email format validation
- URL validation for LinkedIn
- Phone number format validation
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional
from datetime import datetime
import re

from database import get_db
from models import Contact, Company, User
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/contacts", tags=["contacts"])

# Valid relationship types
VALID_RELATIONSHIP_TYPES = {"recruiter", "hiring_manager", "referral", "colleague", "friend", "other"}


class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255, description="Contact name")
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=30)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    company_id: Optional[int] = Field(None, ge=1)
    role: Optional[str] = Field(None, max_length=255)
    relationship_type: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=5000)

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if v:
            # Basic email format validation
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
                raise ValueError("Invalid email format")
        return v

    @field_validator('linkedin_url')
    @classmethod
    def validate_linkedin(cls, v):
        if v:
            if not re.match(r'^https?://(www\.)?linkedin\.com/', v):
                raise ValueError("LinkedIn URL must be a valid LinkedIn profile URL")
        return v

    @field_validator('phone')
    @classmethod
    def validate_phone(cls, v):
        if v:
            # Remove common separators and check for valid phone format
            cleaned = re.sub(r'[\s\-\.\(\)]', '', v)
            if not re.match(r'^\+?[0-9]{7,15}$', cleaned):
                raise ValueError("Invalid phone number format")
        return v


class ContactUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=30)
    linkedin_url: Optional[str] = Field(None, max_length=500)
    company_id: Optional[int] = Field(None, ge=1)
    role: Optional[str] = Field(None, max_length=255)
    relationship_type: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = Field(None, max_length=5000)

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if v:
            if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
                raise ValueError("Invalid email format")
        return v

    @field_validator('linkedin_url')
    @classmethod
    def validate_linkedin(cls, v):
        if v:
            if not re.match(r'^https?://(www\.)?linkedin\.com/', v):
                raise ValueError("LinkedIn URL must be a valid LinkedIn profile URL")
        return v


@router.get("")
async def get_all_contacts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    contacts = db.query(Contact).filter(
        or_(Contact.user_id == current_user.id, Contact.user_id == None)
    ).all()
    result = []
    for contact in contacts:
        result.append({
            "id": contact.id,
            "name": contact.name,
            "email": contact.email,
            "phone": contact.phone,
            "linkedin_url": contact.linkedin_url,
            "company_id": contact.company_id,
            "company_name": contact.company.name if contact.company else None,
            "role": contact.role,
            "relationship_type": contact.relationship_type,
            "notes": contact.notes,
            "created_at": contact.created_at
        })
    return result


@router.get("/{contact_id}")
async def get_contact(
    contact_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    contact = db.query(Contact).filter(
        Contact.id == contact_id,
        or_(Contact.user_id == current_user.id, Contact.user_id == None)
    ).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    return {
        "id": contact.id,
        "name": contact.name,
        "email": contact.email,
        "phone": contact.phone,
        "linkedin_url": contact.linkedin_url,
        "company_id": contact.company_id,
        "company_name": contact.company.name if contact.company else None,
        "role": contact.role,
        "relationship_type": contact.relationship_type,
        "notes": contact.notes,
        "created_at": contact.created_at
    }


@router.get("/company/{company_id}")
async def get_contacts_by_company(
    company_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    contacts = db.query(Contact).filter(
        Contact.company_id == company_id,
        or_(Contact.user_id == current_user.id, Contact.user_id == None)
    ).all()
    result = []
    for contact in contacts:
        result.append({
            "id": contact.id,
            "name": contact.name,
            "email": contact.email,
            "phone": contact.phone,
            "role": contact.role,
            "relationship_type": contact.relationship_type
        })
    return result


@router.post("")
async def create_contact(
    contact: ContactCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if contact.company_id:
        # Verify user can access the company
        company = db.query(Company).filter(
            Company.id == contact.company_id,
            or_(Company.user_id == current_user.id, Company.user_id == None)
        ).first()
        if not company:
            raise HTTPException(status_code=404, detail="Company not found")

    db_contact = Contact(**contact.model_dump(), user_id=current_user.id)
    db.add(db_contact)
    db.commit()
    db.refresh(db_contact)
    return {"id": db_contact.id, "message": "Contact created successfully"}


@router.put("/{contact_id}")
async def update_contact(
    contact_id: int,
    contact: ContactUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    db_contact = db.query(Contact).filter(
        Contact.id == contact_id,
        or_(Contact.user_id == current_user.id, Contact.user_id == None)
    ).first()
    if not db_contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    update_data = contact.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_contact, key, value)

    # Take ownership of shared contacts when updating
    if db_contact.user_id is None:
        db_contact.user_id = current_user.id

    db.commit()
    db.refresh(db_contact)
    return {"message": "Contact updated successfully"}


@router.delete("/{contact_id}")
async def delete_contact(
    contact_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Only allow deleting user's own contacts
    db_contact = db.query(Contact).filter(
        Contact.id == contact_id,
        Contact.user_id == current_user.id
    ).first()
    if not db_contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    db.delete(db_contact)
    db.commit()
    return {"message": "Contact deleted successfully"}
