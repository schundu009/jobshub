"""
User management routes for role-aware job discovery.

Handles user profiles and role selection for relevance scoring.

Security features:
- JWT authentication required for all endpoints
- Admin-only access for user management
- Input length limits
- Email validation
- Salary range validation
- Slug format validation
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, EmailStr, Field, field_validator
from typing import Optional, List
from datetime import datetime
import re

from database import get_db
from models import User, RoleProfile
from services.role_profiles_data import get_all_profiles, get_profile_by_slug
from middleware.auth import get_current_user, get_current_admin

router = APIRouter(prefix="/api/users", tags=["users"])

# Valid seniority levels
VALID_SENIORITY_LEVELS = {"entry", "junior", "mid", "senior", "staff", "principal", "lead", "manager", "director", "vp", "c_level"}


# ============== Pydantic Models ==============

class UserCreate(BaseModel):
    email: str = Field(..., min_length=5, max_length=255)
    name: str = Field(..., min_length=1, max_length=255)
    role_slug: Optional[str] = Field(None, max_length=50)
    target_seniority: Optional[str] = Field(None, max_length=50)
    preferred_locations: Optional[List[str]] = Field(default_factory=list)
    min_salary: Optional[int] = Field(None, ge=0, le=10000000)

    @field_validator('email')
    @classmethod
    def validate_email(cls, v):
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', v):
            raise ValueError("Invalid email format")
        return v

    @field_validator('target_seniority')
    @classmethod
    def validate_seniority(cls, v):
        if v and v not in VALID_SENIORITY_LEVELS:
            raise ValueError(f"Invalid seniority level. Must be one of: {', '.join(VALID_SENIORITY_LEVELS)}")
        return v

    @field_validator('preferred_locations')
    @classmethod
    def validate_locations(cls, v):
        if v:
            if len(v) > 20:
                raise ValueError("Maximum 20 preferred locations allowed")
            for loc in v:
                if len(loc) > 100:
                    raise ValueError("Location name must be 100 characters or less")
        return v


class UserUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    role_slug: Optional[str] = Field(None, max_length=50)
    target_seniority: Optional[str] = Field(None, max_length=50)
    preferred_locations: Optional[List[str]] = None
    min_salary: Optional[int] = Field(None, ge=0, le=10000000)
    custom_preferences: Optional[dict] = None

    @field_validator('target_seniority')
    @classmethod
    def validate_seniority(cls, v):
        if v and v not in VALID_SENIORITY_LEVELS:
            raise ValueError(f"Invalid seniority level. Must be one of: {', '.join(VALID_SENIORITY_LEVELS)}")
        return v

    @field_validator('preferred_locations')
    @classmethod
    def validate_locations(cls, v):
        if v:
            if len(v) > 20:
                raise ValueError("Maximum 20 preferred locations allowed")
            for loc in v:
                if len(loc) > 100:
                    raise ValueError("Location name must be 100 characters or less")
        return v


class RoleProfileCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=50, pattern=r'^[a-z0-9_-]+$')
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    title_patterns: dict = Field(default_factory=dict)
    positive_keywords: dict = Field(default_factory=dict)
    negative_keywords: List[str] = Field(default_factory=list)
    seniority_config: dict = Field(default_factory=dict)
    relevance_threshold: float = Field(30.0, ge=0, le=100)

    @field_validator('negative_keywords')
    @classmethod
    def validate_negative_keywords(cls, v):
        if v:
            if len(v) > 100:
                raise ValueError("Maximum 100 negative keywords allowed")
            for kw in v:
                if len(kw) > 100:
                    raise ValueError("Keyword must be 100 characters or less")
        return v


class RoleProfileUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=1000)
    title_patterns: Optional[dict] = None
    positive_keywords: Optional[dict] = None
    negative_keywords: Optional[List[str]] = None
    seniority_config: Optional[dict] = None
    relevance_threshold: Optional[float] = Field(None, ge=0, le=100)
    is_active: Optional[bool] = None

    @field_validator('negative_keywords')
    @classmethod
    def validate_negative_keywords(cls, v):
        if v:
            if len(v) > 100:
                raise ValueError("Maximum 100 negative keywords allowed")
            for kw in v:
                if len(kw) > 100:
                    raise ValueError("Keyword must be 100 characters or less")
        return v


# ============== User Endpoints ==============

@router.get("")
def list_users(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """List all users. Admin only."""
    users = db.query(User).filter(User.is_active == True).all()

    return {
        "users": [
            {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": {
                    "slug": user.role_profile.slug if user.role_profile else None,
                    "name": user.role_profile.name if user.role_profile else None
                },
                "target_seniority": user.target_seniority,
                "preferred_locations": user.preferred_locations,
                "min_salary": user.min_salary,
                "created_at": user.created_at
            }
            for user in users
        ],
        "total": len(users)
    }


@router.get("/me")
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get current user profile.
    """
    return {
        "id": current_user.id,
        "email": current_user.email,
        "name": current_user.name,
        "role": {
            "slug": current_user.role_profile.slug if current_user.role_profile else None,
            "name": current_user.role_profile.name if current_user.role_profile else None,
            "description": current_user.role_profile.description if current_user.role_profile else None
        } if current_user.role_profile else None,
        "target_seniority": current_user.target_seniority,
        "preferred_locations": current_user.preferred_locations or [],
        "min_salary": current_user.min_salary,
        "custom_preferences": current_user.custom_preferences or {},
        "created_at": current_user.created_at,
        "updated_at": current_user.updated_at
    }


@router.post("")
def create_user(
    user_data: UserCreate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a new user. Admin only."""
    # Check for existing email
    existing = db.query(User).filter(User.email == user_data.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Find role profile if specified
    role_profile_id = None
    if user_data.role_slug:
        role_profile = db.query(RoleProfile).filter(RoleProfile.slug == user_data.role_slug).first()
        if role_profile:
            role_profile_id = role_profile.id

    user = User(
        email=user_data.email,
        name=user_data.name,
        role_profile_id=role_profile_id,
        target_seniority=user_data.target_seniority,
        preferred_locations=user_data.preferred_locations or [],
        min_salary=user_data.min_salary
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return {
        "id": user.id,
        "message": "User created successfully"
    }


@router.put("/{user_id}")
def update_user(
    user_id: int,
    user_data: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update user profile. Users can only update their own profile, admins can update any."""
    # Users can only update their own profile unless they're admin
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Cannot update other users' profiles")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Handle role update
    if user_data.role_slug is not None:
        if user_data.role_slug == "":
            user.role_profile_id = None
        else:
            role_profile = db.query(RoleProfile).filter(RoleProfile.slug == user_data.role_slug).first()
            if role_profile:
                user.role_profile_id = role_profile.id
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Role '{user_data.role_slug}' not found. Use /api/users/roles/seed to create built-in roles first."
                )

    # Update other fields
    if user_data.name is not None:
        user.name = user_data.name
    if user_data.target_seniority is not None:
        user.target_seniority = user_data.target_seniority
    if user_data.preferred_locations is not None:
        user.preferred_locations = user_data.preferred_locations
    if user_data.min_salary is not None:
        user.min_salary = user_data.min_salary
    if user_data.custom_preferences is not None:
        user.custom_preferences = user_data.custom_preferences

    db.commit()

    return {"message": "User updated successfully"}


@router.patch("/{user_id}/role")
def set_user_role(
    user_id: int,
    role_slug: str = Query(..., description="Role profile slug (devops, backend, frontend, etc.)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Set user's role profile for job relevance filtering.

    This is the primary way users configure their job discovery preferences.
    Users can only update their own role, admins can update any.
    """
    # Users can only update their own role unless they're admin
    if current_user.id != user_id and current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Cannot update other users' roles")

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Find role profile
    role_profile = db.query(RoleProfile).filter(RoleProfile.slug == role_slug).first()

    if not role_profile:
        # Check if it's a valid built-in profile
        builtin = get_profile_by_slug(role_slug)
        if not builtin:
            raise HTTPException(
                status_code=400,
                detail=f"Role '{role_slug}' not found. Available: devops, backend, frontend, mobile, data, ml, security, fullstack"
            )

        # Suggest seeding
        raise HTTPException(
            status_code=400,
            detail=f"Role '{role_slug}' exists but needs to be seeded. Call POST /api/users/roles/seed first."
        )

    user.role_profile_id = role_profile.id
    db.commit()

    return {
        "message": f"Role set to '{role_profile.name}'",
        "role": {
            "slug": role_profile.slug,
            "name": role_profile.name
        }
    }


@router.delete("/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Soft delete a user. Admin only."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.is_active = False
    db.commit()

    return {"message": "User deleted successfully"}


# ============== Role Profile Endpoints ==============

@router.get("/roles")
def list_role_profiles(
    include_builtin: bool = Query(True, description="Include built-in profiles not yet in database"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    List all available role profiles.

    Returns both database profiles and optionally built-in profiles.
    """
    # Get database profiles
    db_profiles = db.query(RoleProfile).filter(RoleProfile.is_active == True).all()

    result = []
    db_slugs = set()

    for profile in db_profiles:
        result.append({
            "id": profile.id,
            "slug": profile.slug,
            "name": profile.name,
            "description": profile.description,
            "relevance_threshold": profile.relevance_threshold,
            "source": "database",
            "created_at": profile.created_at
        })
        db_slugs.add(profile.slug)

    # Add built-in profiles not in database
    if include_builtin:
        for profile in get_all_profiles():
            if profile["slug"] not in db_slugs:
                result.append({
                    "id": None,
                    "slug": profile["slug"],
                    "name": profile["name"],
                    "description": profile["description"],
                    "relevance_threshold": profile.get("relevance_threshold", 30.0),
                    "source": "builtin",
                    "created_at": None
                })

    return {
        "roles": result,
        "total": len(result)
    }


@router.post("/roles/seed")
def seed_role_profiles(
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """
    Seed the database with built-in role profiles. Admin only.

    This creates database records for all predefined role profiles,
    making them available for user assignment.
    """
    builtin_profiles = get_all_profiles()
    created = 0
    skipped = 0

    for profile_data in builtin_profiles:
        # Check if exists
        existing = db.query(RoleProfile).filter(RoleProfile.slug == profile_data["slug"]).first()
        if existing:
            skipped += 1
            continue

        # Create profile
        profile = RoleProfile(
            slug=profile_data["slug"],
            name=profile_data["name"],
            description=profile_data["description"],
            title_patterns=profile_data["title_patterns"],
            positive_keywords=profile_data["positive_keywords"],
            negative_keywords=profile_data["negative_keywords"],
            seniority_config=profile_data.get("seniority_config", {}),
            relevance_threshold=profile_data.get("relevance_threshold", 30.0)
        )
        db.add(profile)
        created += 1

    db.commit()

    return {
        "message": f"Seeded {created} role profiles",
        "created": created,
        "skipped": skipped
    }


@router.get("/roles/{role_slug}")
def get_role_profile(
    role_slug: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get detailed information about a role profile."""
    # Check database first
    profile = db.query(RoleProfile).filter(RoleProfile.slug == role_slug).first()

    if profile:
        return {
            "id": profile.id,
            "slug": profile.slug,
            "name": profile.name,
            "description": profile.description,
            "title_patterns": profile.title_patterns,
            "positive_keywords": profile.positive_keywords,
            "negative_keywords": profile.negative_keywords,
            "seniority_config": profile.seniority_config,
            "relevance_threshold": profile.relevance_threshold,
            "is_active": profile.is_active,
            "source": "database",
            "created_at": profile.created_at,
            "updated_at": profile.updated_at
        }

    # Check built-in
    builtin = get_profile_by_slug(role_slug)
    if builtin:
        return {
            "id": None,
            "slug": builtin["slug"],
            "name": builtin["name"],
            "description": builtin["description"],
            "title_patterns": builtin["title_patterns"],
            "positive_keywords": builtin["positive_keywords"],
            "negative_keywords": builtin["negative_keywords"],
            "seniority_config": builtin.get("seniority_config", {}),
            "relevance_threshold": builtin.get("relevance_threshold", 30.0),
            "is_active": True,
            "source": "builtin",
            "created_at": None,
            "updated_at": None
        }

    raise HTTPException(status_code=404, detail=f"Role profile '{role_slug}' not found")


@router.post("/roles")
def create_role_profile(
    profile_data: RoleProfileCreate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Create a custom role profile. Admin only."""
    # Check for existing slug
    existing = db.query(RoleProfile).filter(RoleProfile.slug == profile_data.slug).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Role '{profile_data.slug}' already exists")

    profile = RoleProfile(
        slug=profile_data.slug,
        name=profile_data.name,
        description=profile_data.description,
        title_patterns=profile_data.title_patterns,
        positive_keywords=profile_data.positive_keywords,
        negative_keywords=profile_data.negative_keywords,
        seniority_config=profile_data.seniority_config,
        relevance_threshold=profile_data.relevance_threshold
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)

    return {
        "id": profile.id,
        "message": f"Role profile '{profile.name}' created successfully"
    }


@router.put("/roles/{role_slug}")
def update_role_profile(
    role_slug: str,
    profile_data: RoleProfileUpdate,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Update a role profile. Admin only."""
    profile = db.query(RoleProfile).filter(RoleProfile.slug == role_slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Role profile '{role_slug}' not found")

    # Update fields
    if profile_data.name is not None:
        profile.name = profile_data.name
    if profile_data.description is not None:
        profile.description = profile_data.description
    if profile_data.title_patterns is not None:
        profile.title_patterns = profile_data.title_patterns
    if profile_data.positive_keywords is not None:
        profile.positive_keywords = profile_data.positive_keywords
    if profile_data.negative_keywords is not None:
        profile.negative_keywords = profile_data.negative_keywords
    if profile_data.seniority_config is not None:
        profile.seniority_config = profile_data.seniority_config
    if profile_data.relevance_threshold is not None:
        profile.relevance_threshold = profile_data.relevance_threshold
    if profile_data.is_active is not None:
        profile.is_active = profile_data.is_active

    db.commit()

    return {"message": f"Role profile '{role_slug}' updated successfully"}


@router.delete("/roles/{role_slug}")
def delete_role_profile(
    role_slug: str,
    current_user: User = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """Soft delete a role profile. Admin only."""
    profile = db.query(RoleProfile).filter(RoleProfile.slug == role_slug).first()
    if not profile:
        raise HTTPException(status_code=404, detail=f"Role profile '{role_slug}' not found")

    # Check if any users are using this profile
    users_count = db.query(User).filter(User.role_profile_id == profile.id).count()
    if users_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete: {users_count} user(s) are using this role profile"
        )

    profile.is_active = False
    db.commit()

    return {"message": f"Role profile '{role_slug}' deleted successfully"}
