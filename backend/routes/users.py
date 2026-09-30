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
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
import re

from database import get_db
from models import User, RoleProfile, UserDocument
from services.role_profiles_data import get_profile_by_slug
from middleware.auth import get_current_user, get_current_admin
from fastapi import UploadFile, File
import os
import uuid

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


# ============== Job Roles Endpoints ==============

# ============== Onboarding Endpoints ==============

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


# ============== User Settings Endpoints ==============
# NOTE: These must be defined BEFORE /{user_id} routes to avoid path conflicts

# Upload directory for user documents
UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads", "user_documents")
os.makedirs(UPLOAD_DIR, exist_ok=True)


def extract_text_from_file(file_content: bytes, filename: str) -> tuple[str, str]:
    """Extract text content from uploaded file. Returns (content, error_message)."""
    import io
    file_ext = os.path.splitext(filename)[1].lower()
    content = ""
    error_msg = ""

    try:
        if file_ext == '.txt':
            content = file_content.decode('utf-8', errors='ignore')
        elif file_ext == '.pdf':
            try:
                import pdfplumber
                with pdfplumber.open(io.BytesIO(file_content)) as pdf:
                    content = '\n'.join(page.extract_text() or '' for page in pdf.pages)
            except ImportError:
                try:
                    import PyPDF2
                    reader = PyPDF2.PdfReader(io.BytesIO(file_content))
                    content = '\n'.join(page.extract_text() or '' for page in reader.pages)
                except ImportError:
                    error_msg = "PDF libraries not available"
                    print(f"PDF extraction failed: {error_msg}")
        elif file_ext in ['.doc', '.docx']:
            try:
                import docx
                doc_file = docx.Document(io.BytesIO(file_content))
                # Extract text from paragraphs
                paragraphs = [para.text for para in doc_file.paragraphs if para.text.strip()]
                # Extract text from tables
                table_text = []
                for table in doc_file.tables:
                    for row in table.rows:
                        row_text = [cell.text.strip() for cell in row.cells if cell.text.strip()]
                        if row_text:
                            table_text.append(' | '.join(row_text))
                # Combine paragraphs and tables
                all_text = paragraphs + table_text
                content = '\n'.join(all_text)
                print(f"DOCX extraction: {len(paragraphs)} paragraphs, {len(table_text)} table rows, {len(content)} chars")
            except ImportError as e:
                error_msg = f"python-docx not installed: {e}"
                print(f"DOCX extraction failed: {error_msg}")
            except Exception as e:
                error_msg = f"DOCX parsing error: {e}"
                print(f"DOCX extraction error: {error_msg}")
        elif file_ext == '.rtf':
            content = file_content.decode('utf-8', errors='ignore')
        else:
            content = file_content.decode('utf-8', errors='ignore')
    except Exception as e:
        error_msg = f"General extraction error: {e}"
        print(f"Error extracting text from {filename}: {e}")

    return content.strip(), error_msg


@router.post("/documents")
async def upload_document(
    document_type: str = Query(..., description="Type of document: resume or cover_letter"),
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Upload a resume or cover letter."""
    if document_type not in ["resume", "cover_letter"]:
        raise HTTPException(status_code=400, detail="Invalid document type. Must be 'resume' or 'cover_letter'")
    allowed_extensions = {".pdf", ".doc", ".docx", ".txt", ".rtf"}
    file_ext = os.path.splitext(file.filename)[1].lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Invalid file type. Allowed: PDF, DOC, DOCX, TXT, RTF")
    content = await file.read()
    file_size = len(content)
    if file_size > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 5MB")

    # Save file locally first
    unique_filename = f"{current_user.id}_{uuid.uuid4().hex}{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)
    try:
        with open(file_path, "wb") as f:
            f.write(content)
    except Exception as e:
        print(f"File storage failed: {e}")
        file_path = None

    # Extract text content from the file (non-blocking - allow upload even if extraction fails)
    extracted_text, error_msg = extract_text_from_file(content, file.filename)
    extraction_warning = None
    if not extracted_text and error_msg:
        extraction_warning = f"File uploaded but text extraction failed: {error_msg}"
        print(f"Text extraction warning for {file.filename}: {error_msg}")

    existing_docs = db.query(UserDocument).filter(
        UserDocument.user_id == current_user.id,
        UserDocument.document_type == document_type
    ).count()
    doc = UserDocument(
        user_id=current_user.id,
        document_type=document_type,
        filename=file.filename,
        file_path=file_path,
        file_size=file_size,
        mime_type=file.content_type,
        content_text=extracted_text or "",  # Store extracted text in DB (empty string if extraction failed)
        is_default=(existing_docs == 0)
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    response = {
        "id": doc.id,
        "filename": doc.filename,
        "document_type": doc.document_type,
        "file_size": doc.file_size,
        "is_default": doc.is_default,
        "created_at": doc.created_at,
        "message": "Document uploaded successfully"
    }
    if extraction_warning:
        response["warning"] = extraction_warning
    return response


@router.get("/documents")
def list_documents(
    type: Optional[str] = Query(None, description="Filter by document type: resume or cover_letter"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """List user's uploaded documents."""
    query = db.query(UserDocument).filter(UserDocument.user_id == current_user.id)
    if type:
        query = query.filter(UserDocument.document_type == type)
    documents = query.order_by(UserDocument.is_default.desc(), UserDocument.created_at.desc()).all()
    return [
        {
            "id": doc.id,
            "filename": doc.filename,
            "document_type": doc.document_type,
            "file_size": doc.file_size,
            "is_default": doc.is_default,
            "created_at": doc.created_at
        }
        for doc in documents
    ]


@router.get("/documents/default-resume")
def get_default_resume_content(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the content of the user's default resume."""
    doc = db.query(UserDocument).filter(
        UserDocument.user_id == current_user.id,
        UserDocument.document_type == "resume",
        UserDocument.is_default == True
    ).first()

    if not doc:
        # Try to get any resume if no default is set
        doc = db.query(UserDocument).filter(
            UserDocument.user_id == current_user.id,
            UserDocument.document_type == "resume"
        ).order_by(UserDocument.created_at.desc()).first()

    if not doc:
        raise HTTPException(status_code=404, detail="No resume found. Please upload a resume first.")

    # Use stored content_text from database (works on cloud deployments)
    content = doc.content_text

    # If no stored content, try to read from file (local development fallback)
    if not content and doc.file_path and os.path.exists(doc.file_path):
        file_ext = os.path.splitext(doc.filename)[1].lower()
        try:
            if file_ext == '.txt':
                with open(doc.file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            elif file_ext == '.pdf':
                try:
                    import pdfplumber
                    with pdfplumber.open(doc.file_path) as pdf:
                        content = '\n'.join(page.extract_text() or '' for page in pdf.pages)
                except ImportError:
                    try:
                        import PyPDF2
                        with open(doc.file_path, 'rb') as f:
                            reader = PyPDF2.PdfReader(f)
                            content = '\n'.join(page.extract_text() or '' for page in reader.pages)
                    except ImportError:
                        pass
            elif file_ext in ['.doc', '.docx']:
                try:
                    import docx
                    doc_file = docx.Document(doc.file_path)
                    content = '\n'.join(para.text for para in doc_file.paragraphs)
                except ImportError:
                    pass
            else:
                with open(doc.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
        except Exception:
            pass

    if not content or not content.strip():
        raise HTTPException(
            status_code=400,
            detail="Resume content not available. Please re-upload your resume to enable text extraction."
        )

    return {
        "id": doc.id,
        "filename": doc.filename,
        "content": content,
        "document_type": doc.document_type,
        "is_default": doc.is_default
    }


@router.get("/documents/{doc_id}/content")
def get_document_content(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get the content of a specific document."""
    doc = db.query(UserDocument).filter(
        UserDocument.id == doc_id,
        UserDocument.user_id == current_user.id
    ).first()

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # Use stored content_text from database (works on cloud deployments)
    content = doc.content_text

    # If no stored content, try to read from file (local development fallback)
    if not content and doc.file_path and os.path.exists(doc.file_path):
        file_ext = os.path.splitext(doc.filename)[1].lower()
        try:
            if file_ext == '.txt':
                with open(doc.file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
            elif file_ext == '.pdf':
                try:
                    import pdfplumber
                    with pdfplumber.open(doc.file_path) as pdf:
                        content = '\n'.join(page.extract_text() or '' for page in pdf.pages)
                except ImportError:
                    try:
                        import PyPDF2
                        with open(doc.file_path, 'rb') as f:
                            reader = PyPDF2.PdfReader(f)
                            content = '\n'.join(page.extract_text() or '' for page in reader.pages)
                    except ImportError:
                        pass
            elif file_ext in ['.doc', '.docx']:
                try:
                    import docx
                    doc_file = docx.Document(doc.file_path)
                    content = '\n'.join(para.text for para in doc_file.paragraphs)
                except ImportError:
                    pass
            else:
                with open(doc.file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
        except Exception:
            pass

    if not content or not content.strip():
        raise HTTPException(
            status_code=400,
            detail="Document content not available. Please re-upload the document to enable text extraction."
        )

    return {
        "id": doc.id,
        "filename": doc.filename,
        "content": content,
        "document_type": doc.document_type
    }


@router.put("/documents/{doc_id}/default")
def set_default_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Set a document as the default for its type."""
    doc = db.query(UserDocument).filter(
        UserDocument.id == doc_id,
        UserDocument.user_id == current_user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    db.query(UserDocument).filter(
        UserDocument.user_id == current_user.id,
        UserDocument.document_type == doc.document_type,
        UserDocument.id != doc_id
    ).update({"is_default": False})
    doc.is_default = True
    db.commit()
    return {"message": "Default document updated"}


@router.delete("/documents/{doc_id}")
def delete_document(
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a user's document."""
    doc = db.query(UserDocument).filter(
        UserDocument.id == doc_id,
        UserDocument.user_id == current_user.id
    ).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    if doc.file_path and os.path.exists(doc.file_path):
        try:
            os.remove(doc.file_path)
        except OSError:
            pass
    was_default = doc.is_default
    doc_type = doc.document_type
    # Clear dangling base-resume reference (FK to user_documents)
    db.query(User).filter(
        User.id == current_user.id, User.base_resume_id == doc.id
    ).update({"base_resume_id": None}, synchronize_session=False)
    db.delete(doc)
    db.commit()
    if was_default:
        next_doc = db.query(UserDocument).filter(
            UserDocument.user_id == current_user.id,
            UserDocument.document_type == doc_type
        ).first()
        if next_doc:
            next_doc.is_default = True
            db.commit()
    return {"message": "Document deleted"}


# ============== User CRUD Endpoints ==============

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

# ============== One-time Admin Setup Endpoint ==============
