"""
Document management routes with secure file upload handling.

Security features:
- JWT authentication required for all endpoints
- File type validation (whitelist of allowed MIME types and extensions)
- File size limits
- Filename sanitization
- Secure storage with UUID-based filenames
- User-scoped document access (multi-tenancy)
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import Optional
import os
import uuid
import re

from database import get_db
from models import Document, Job, User
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/documents", tags=["documents"])

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPLOAD_DIR = os.path.join(BASE_DIR, "data", "uploads")

if not os.path.exists(UPLOAD_DIR):
    os.makedirs(UPLOAD_DIR)

# =============================================================================
# File Upload Security Configuration
# =============================================================================

# Maximum file size in bytes (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024

# Allowed file extensions (whitelist)
ALLOWED_EXTENSIONS = {
    ".pdf",
    ".doc",
    ".docx",
    ".txt",
    ".rtf",
    ".odt",
    ".png",
    ".jpg",
    ".jpeg",
}

# Allowed MIME types (whitelist)
ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
    "text/rtf",
    "application/rtf",
    "application/vnd.oasis.opendocument.text",
    "image/png",
    "image/jpeg",
}

# Valid document types
VALID_DOC_TYPES = {"resume", "cover_letter", "portfolio", "other"}


def validate_file_extension(filename: str) -> str:
    """Validate and return the file extension."""
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    ext = os.path.splitext(filename.lower())[1]
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    return ext


def validate_mime_type(content_type: str) -> None:
    """Validate the MIME type."""
    if content_type and content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"MIME type not allowed: {content_type}"
        )


def validate_file_size(content: bytes) -> None:
    """Validate file size."""
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB"
        )


def sanitize_name(name: str) -> str:
    """Sanitize document name to prevent injection attacks."""
    # Remove any path separators and special characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', name)
    # Limit length
    return sanitized[:255] if sanitized else "unnamed"


def validate_doc_type(doc_type: str) -> str:
    """Validate document type."""
    doc_type_lower = doc_type.lower()
    if doc_type_lower not in VALID_DOC_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document type. Allowed types: {', '.join(VALID_DOC_TYPES)}"
        )
    return doc_type_lower


# =============================================================================
# Routes
# =============================================================================

@router.get("")
def get_all_documents(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all documents for the current user."""
    documents = (
        db.query(Document)
        .join(Job, Document.job_id == Job.id, isouter=True)
        .filter(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
        .all()
    )
    result = []
    for doc in documents:
        result.append({
            "id": doc.id,
            "name": doc.name,
            "doc_type": doc.doc_type,
            "job_id": doc.job_id,
            "job_title": doc.job.title if doc.job else None,
            "created_at": doc.created_at
        })
    return result


@router.get("/job/{job_id}")
def get_documents_by_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get documents for a specific job owned by the current user."""
    # Verify job belongs to user
    job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    documents = db.query(Document).filter(
        Document.job_id == job_id, Document.user_id == current_user.id
    ).all()
    result = []
    for doc in documents:
        result.append({
            "id": doc.id,
            "name": doc.name,
            "doc_type": doc.doc_type,
            "created_at": doc.created_at
        })
    return result


@router.post("")
async def upload_document(
    file: UploadFile = File(...),
    name: str = Form(..., min_length=1, max_length=255),
    doc_type: str = Form(...),
    job_id: Optional[int] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Upload a document with security validation.

    - Requires JWT authentication
    - Validates file extension against whitelist
    - Validates MIME type
    - Enforces file size limit (10 MB)
    - Sanitizes filename and document name
    - Stores with UUID-based filename to prevent collisions
    """
    # Validate job exists and belongs to user if provided
    if job_id:
        job = db.query(Job).filter(Job.id == job_id, Job.user_id == current_user.id).first()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")

    # Validate file extension
    file_extension = validate_file_extension(file.filename)

    # Validate MIME type
    validate_mime_type(file.content_type)

    # Validate document type
    validated_doc_type = validate_doc_type(doc_type)

    # Sanitize document name
    sanitized_name = sanitize_name(name)

    # Generate secure filename
    unique_filename = f"{uuid.uuid4()}{file_extension}"
    file_path = os.path.join(UPLOAD_DIR, unique_filename)

    # Stream file and validate size while writing (prevents memory exhaustion)
    total_size = 0
    chunk_size = 64 * 1024  # 64KB chunks

    with open(file_path, "wb") as f:
        while True:
            chunk = await file.read(chunk_size)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > MAX_FILE_SIZE:
                # File too large - delete partial file and raise error
                f.close()
                try:
                    os.remove(file_path)
                except OSError:
                    pass
                raise HTTPException(
                    status_code=413,
                    detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB"
                )
            f.write(chunk)

    # Create database record
    db_document = Document(
        user_id=current_user.id,
        name=sanitized_name,
        doc_type=validated_doc_type,
        job_id=job_id,
        file_path=file_path
    )
    db.add(db_document)
    db.commit()
    db.refresh(db_document)

    return {
        "id": db_document.id,
        "name": db_document.name,
        "message": "Document uploaded successfully"
    }


@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a document and its file. Only owner can delete."""
    db_document = (
        db.query(Document)
        .join(Job, Document.job_id == Job.id, isouter=True)
        .filter(
            Document.id == document_id,
            Document.user_id == current_user.id
        )
        .first()
    )
    if not db_document:
        raise HTTPException(status_code=404, detail="Document not found")

    # Delete file if exists - with path traversal protection
    if db_document.file_path:
        # Resolve to absolute path and verify it's within UPLOAD_DIR
        try:
            real_path = os.path.realpath(db_document.file_path)
            upload_dir_real = os.path.realpath(UPLOAD_DIR)

            # Security check: ensure file is within upload directory
            if real_path.startswith(upload_dir_real + os.sep) and os.path.exists(real_path):
                os.remove(real_path)
        except (OSError, ValueError):
            pass  # File may already be deleted or path invalid

    db.delete(db_document)
    db.commit()
    return {"message": "Document deleted successfully"}
