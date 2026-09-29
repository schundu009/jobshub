"""
Note management routes with input validation.

Security features:
- Input length limits
- Enum validation for note types
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from pydantic import BaseModel, Field, field_validator
from typing import Optional

from database import get_db
from models import Note, Job, User
from middleware.auth import get_current_user

router = APIRouter(prefix="/api/notes", tags=["notes"])

# Valid note types
VALID_NOTE_TYPES = {"general", "interview_prep", "research", "follow_up", "feedback", "other"}


class NoteCreate(BaseModel):
    job_id: int = Field(..., ge=1)
    content: str = Field(..., min_length=1, max_length=50000)
    note_type: Optional[str] = Field("general", max_length=50)

    @field_validator('note_type')
    @classmethod
    def validate_note_type(cls, v):
        if v and v not in VALID_NOTE_TYPES:
            raise ValueError(f"Invalid note type. Must be one of: {', '.join(VALID_NOTE_TYPES)}")
        return v


class NoteUpdate(BaseModel):
    content: Optional[str] = Field(None, min_length=1, max_length=50000)
    note_type: Optional[str] = Field(None, max_length=50)

    @field_validator('note_type')
    @classmethod
    def validate_note_type(cls, v):
        if v and v not in VALID_NOTE_TYPES:
            raise ValueError(f"Invalid note type. Must be one of: {', '.join(VALID_NOTE_TYPES)}")
        return v


@router.get("")
def get_all_notes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get notes for jobs owned by the user
    notes = db.query(Note).join(Job).filter(
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).order_by(Note.created_at.desc()).all()
    result = []
    for note in notes:
        result.append({
            "id": note.id,
            "job_id": note.job_id,
            "job_title": note.job.title if note.job else None,
            "content": note.content,
            "note_type": note.note_type,
            "created_at": note.created_at
        })
    return result


@router.get("/job/{job_id}")
def get_notes_by_job(
    job_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify user has access to this job
    job = db.query(Job).filter(
        Job.id == job_id,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    notes = db.query(Note).filter(Note.job_id == job_id).order_by(Note.created_at.desc()).all()
    result = []
    for note in notes:
        result.append({
            "id": note.id,
            "content": note.content,
            "note_type": note.note_type,
            "created_at": note.created_at
        })
    return result


@router.post("")
def create_note(
    note: NoteCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Verify user has access to this job
    job = db.query(Job).filter(
        Job.id == note.job_id,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    db_note = Note(**note.model_dump())
    db.add(db_note)

    # Take ownership of shared job when adding note
    if job.user_id is None:
        job.user_id = current_user.id

    db.commit()
    db.refresh(db_note)
    return {"id": db_note.id, "message": "Note created successfully"}


@router.put("/{note_id}")
def update_note(
    note_id: int,
    note: NoteUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Get note and verify access through job ownership
    db_note = db.query(Note).join(Job).filter(
        Note.id == note_id,
        or_(Job.user_id == current_user.id, Job.user_id == None)
    ).first()
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")

    update_data = note.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_note, key, value)

    db.commit()
    db.refresh(db_note)
    return {"message": "Note updated successfully"}


@router.delete("/{note_id}")
def delete_note(
    note_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Only allow deleting notes for user's own jobs
    db_note = db.query(Note).join(Job).filter(
        Note.id == note_id,
        Job.user_id == current_user.id
    ).first()
    if not db_note:
        raise HTTPException(status_code=404, detail="Note not found")

    db.delete(db_note)
    db.commit()
    return {"message": "Note deleted successfully"}
