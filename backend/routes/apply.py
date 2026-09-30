"""
Cariara Auto Apply API (/api/apply).

Cariara prepares applications; the customer (or the Cariara browser extension,
Phase 2) submits them. No endpoint here submits anything to an employer.
"""
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from database import get_db
from middleware.auth import get_current_user
from models import AnswerBankEntry, Application, ApplyQueueItem, Job, User, UserDocument
from services.apply import service as svc
from services.apply.constants import (
    EDITABLE_STATUSES, PLAN_REQUIRED_DETAIL, STATUSES, SUPPORTED_ATS,
)
from services.apply.resolver import normalize_question_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/apply", tags=["auto-apply"])


# --------------------------------------------------------------------------- schemas

class PreferencesUpdate(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[Literal["review", "auto"]] = None
    min_match_score: Optional[int] = Field(default=None, ge=0, le=100)
    daily_cap: Optional[int] = Field(default=None, ge=1, le=500)
    target_roles: Optional[List[str]] = Field(default=None, max_length=20)
    locations: Optional[List[str]] = Field(default=None, max_length=30)
    remote_ok: Optional[bool] = None
    salary_floor: Optional[int] = Field(default=None, ge=0)
    excluded_companies: Optional[List[str]] = Field(default=None, max_length=200)
    ats_allowlist: Optional[List[str]] = None

    @field_validator("ats_allowlist")
    @classmethod
    def _allowlist(cls, value):
        if value is None:
            return value
        bad = [v for v in value if v not in SUPPORTED_ATS]
        if bad:
            raise ValueError(f"Unsupported ATS: {', '.join(bad)}. Allowed: {', '.join(SUPPORTED_ATS)}")
        return list(dict.fromkeys(value))


class LocationIn(BaseModel):
    city: Optional[str] = Field(default=None, max_length=100)
    state: Optional[str] = Field(default=None, max_length=100)
    country: Optional[str] = Field(default=None, max_length=50)


class EeoIn(BaseModel):
    opt_in: Optional[bool] = None
    gender: Optional[str] = Field(default=None, max_length=20)
    race: Optional[str] = Field(default=None, max_length=50)
    veteran: Optional[str] = Field(default=None, max_length=30)
    disability: Optional[str] = Field(default=None, max_length=20)


class ProfileUpdate(BaseModel):
    first_name: Optional[str] = Field(default=None, max_length=100)
    last_name: Optional[str] = Field(default=None, max_length=100)
    email: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=50)
    location: Optional[LocationIn] = None
    linkedin: Optional[str] = Field(default=None, max_length=500)
    github: Optional[str] = Field(default=None, max_length=500)
    portfolio: Optional[str] = Field(default=None, max_length=500)
    work_authorized_us: Optional[bool] = None
    requires_sponsorship: Optional[bool] = None
    willing_to_relocate: Optional[bool] = None
    earliest_start_date: Optional[str] = None
    salary_expectation: Optional[str] = Field(default=None, max_length=100)
    notice_period: Optional[str] = Field(default=None, max_length=100)
    eeo: Optional[EeoIn] = None

    @field_validator("earliest_start_date")
    @classmethod
    def _date(cls, value):
        if value:
            datetime.strptime(value, "%Y-%m-%d")
        return value


class CreateApplication(BaseModel):
    job_id: int


class AnswersUpdate(BaseModel):
    answers: Dict[str, Any]
    save_to_bank: bool = False


class ApplicationUpdate(BaseModel):
    resume_doc_id: Optional[int] = None
    cover_letter_text: Optional[str] = Field(default=None, max_length=20000)


class MarkSubmitted(BaseModel):
    confirmation: Optional[str] = Field(default=None, max_length=500)


class SkipIn(BaseModel):
    reason: Optional[str] = Field(default=None, max_length=500)


class BankIn(BaseModel):
    label: str = Field(min_length=1, max_length=2000)
    value: str = Field(max_length=20000)
    sensitive: Optional[bool] = False


class BankUpdate(BaseModel):
    label: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    value: Optional[str] = Field(default=None, max_length=20000)
    sensitive: Optional[bool] = None


class ExtensionResult(BaseModel):
    status: Literal["submitted", "failed", "captcha"]
    confirmation: Optional[str] = Field(default=None, max_length=500)
    error: Optional[str] = Field(default=None, max_length=2000)


# --------------------------------------------------------------------------- helpers

def _payment_required() -> JSONResponse:
    return JSONResponse(status_code=402, content={"detail": PLAN_REQUIRED_DETAIL})


def _require_plan(db: Session, user: User) -> Optional[JSONResponse]:
    if not svc.plan_for(db, user).plan_ok:
        return _payment_required()
    return None


def _get_app(db: Session, user: User, app_id: int) -> Application:
    app = (db.query(Application).options(joinedload(Application.job).joinedload(Job.company))
           .filter(Application.id == app_id, Application.user_id == user.id).first())
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


def _detail(db: Session, app: Application, user: User) -> Dict[str, Any]:
    db.refresh(app)
    return svc.application_detail(db, app, user)


def _conflict(message: str) -> HTTPException:
    return HTTPException(status_code=409, detail=message)


# --------------------------------------------------------------------------- preferences / profile

@router.get("/preferences")
def get_preferences(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    prefs = svc.get_preferences(db, current_user)
    return svc.preferences_payload(prefs, svc.plan_for(db, current_user, prefs))


@router.put("/preferences")
def put_preferences(body: PreferencesUpdate, current_user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    prefs = svc.get_preferences(db, current_user)
    plan = svc.plan_for(db, current_user, prefs)
    data = body.model_dump(exclude_unset=True)
    if not plan.plan_ok and (data.get("enabled") is True or data.get("mode") == "auto"):
        return _payment_required()
    for key, value in data.items():
        if key in ("target_roles", "locations", "excluded_companies"):
            value = [v.strip() for v in (value or []) if v and v.strip()]
        if key in ("enabled", "mode", "min_match_score", "daily_cap", "remote_ok") and value is None:
            continue
        setattr(prefs, key, value)
    if plan.plan_ok and prefs.daily_cap and prefs.daily_cap > plan.daily_cap_max:
        prefs.daily_cap = plan.daily_cap_max
    db.commit()
    db.refresh(prefs)
    return svc.preferences_payload(prefs, plan)


@router.get("/profile")
def get_profile(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    ap = svc.get_apply_profile(db, current_user)
    db.commit()
    return svc.profile_payload(current_user, ap)


@router.put("/profile")
def put_profile(body: ProfileUpdate, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    data = body.model_dump(exclude_unset=True)
    svc.update_profile(db, current_user, data)
    db.refresh(current_user)
    return svc.profile_payload(current_user, svc.get_apply_profile(db, current_user))


@router.get("/readiness")
def get_readiness(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.readiness(db, current_user)


# --------------------------------------------------------------------------- queue

def _refresh_queue_inline(user_id: int) -> None:
    from tasks.apply_tasks import prepare_for_user_sync, refresh_queue_for_user_sync

    refresh_queue_for_user_sync(user_id)
    prepare_for_user_sync(user_id)


@router.get("/queue")
def get_queue(limit: int = Query(50, ge=1, le=100), current_user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    prefs = svc.get_preferences(db, current_user)
    if prefs.queue_generated_at is None:
        # First visit: build synchronously so the page is not empty.
        from tasks.apply_tasks import build_queue_for

        build_queue_for(db, current_user)
        db.refresh(prefs)
    applied = db.query(Application.job_id).filter(Application.user_id == current_user.id)
    items = (db.query(ApplyQueueItem)
             .options(joinedload(ApplyQueueItem.job).joinedload(Job.company))
             .filter(ApplyQueueItem.user_id == current_user.id, ~ApplyQueueItem.job_id.in_(applied))
             .order_by(ApplyQueueItem.match_score.desc(), ApplyQueueItem.id.asc())
             .limit(limit).all())
    return {
        "items": [{"job": svc.job_payload(item.job, item.ats), "match_score": item.match_score,
                   "reasons": item.reasons or []} for item in items if item.job is not None],
        "generated_at": prefs.queue_generated_at.isoformat() if prefs.queue_generated_at else None,
    }


@router.post("/queue/refresh")
def refresh_queue(background: BackgroundTasks, current_user: User = Depends(get_current_user)):
    from tasks.apply_tasks import refresh_queue_for_user

    if os.getenv("APPLY_INLINE_TASKS", "").lower() in ("1", "true", "yes"):
        # Local dev without a Celery worker.
        background.add_task(_refresh_queue_inline, current_user.id)
        return {"status": "queued"}
    try:
        refresh_queue_for_user.apply_async(args=[current_user.id], retry=False)
    except Exception as e:  # broker down: do it in-process after the response
        logger.info("queue refresh falling back to in-process: %s", e)
        background.add_task(_refresh_queue_inline, current_user.id)
    return {"status": "queued"}


# --------------------------------------------------------------------------- applications

@router.post("/applications", status_code=201)
def create_application(body: CreateApplication, current_user: User = Depends(get_current_user),
                       db: Session = Depends(get_db)):
    existing = db.query(Application).filter(Application.user_id == current_user.id,
                                            Application.job_id == body.job_id).first()
    if existing:
        return JSONResponse(status_code=409, content={
            "detail": "You already have an application for this job", "id": existing.id})
    prefs = svc.get_preferences(db, current_user)
    plan = svc.plan_for(db, current_user, prefs)
    if not plan.plan_ok:
        return _payment_required()
    job = db.query(Job).filter(Job.id == body.job_id).first()
    if job is None or (job.user_id is not None and job.user_id != current_user.id):
        raise HTTPException(status_code=404, detail="Job not found")
    cap = svc.effective_daily_cap(prefs, plan)
    if svc.today_count(db, current_user.id) >= cap:
        return JSONResponse(status_code=429, content={
            "detail": f"Daily limit reached ({cap} applications per day)",
            "resets_at": svc.next_reset().isoformat() + "Z"})
    try:
        app = svc.create_application(db, current_user, job, created_by="user")
    except IntegrityError:
        db.rollback()
        existing = db.query(Application).filter(Application.user_id == current_user.id,
                                                Application.job_id == body.job_id).first()
        return JSONResponse(status_code=409, content={
            "detail": "You already have an application for this job", "id": existing.id if existing else None})
    return _detail(db, app, current_user)


@router.get("/applications")
def list_applications(status: Optional[str] = None, limit: int = Query(50, ge=1, le=200),
                      offset: int = Query(0, ge=0), current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    query = db.query(Application).filter(Application.user_id == current_user.id)
    if status:
        wanted = [s.strip() for s in status.split(",") if s.strip()]
        unknown = [s for s in wanted if s not in STATUSES]
        if unknown:
            raise HTTPException(status_code=400, detail=f"Unknown status: {', '.join(unknown)}")
        query = query.filter(Application.status.in_(wanted))
    total = query.count()
    rows = (query.options(joinedload(Application.job).joinedload(Job.company))
            .order_by(Application.updated_at.desc(), Application.id.desc())
            .offset(offset).limit(limit).all())
    return {"items": [svc.application_summary(a) for a in rows], "total": total}


@router.get("/applications/{app_id}")
def get_application(app_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return svc.application_detail(db, _get_app(db, current_user, app_id), current_user)


@router.patch("/applications/{app_id}/answers")
def patch_answers(app_id: int, body: AnswersUpdate, current_user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    app = _get_app(db, current_user, app_id)
    if app.status not in EDITABLE_STATUSES:
        raise _conflict(f"Answers can't be changed while the application is {app.status}")
    unknown = svc.apply_user_answers(db, app, current_user, body.answers, body.save_to_bank)
    if unknown:
        return JSONResponse(status_code=400, content={"detail": "Unknown question id(s)", "missing": unknown})
    return _detail(db, app, current_user)


@router.patch("/applications/{app_id}")
def patch_application(app_id: int, body: ApplicationUpdate, current_user: User = Depends(get_current_user),
                      db: Session = Depends(get_db)):
    app = _get_app(db, current_user, app_id)
    if app.status in ("submitted", "confirmed", "withdrawn"):
        raise _conflict(f"Application is already {app.status}")
    data = body.model_dump(exclude_unset=True)
    changes = []
    if "resume_doc_id" in data:
        doc_id = data["resume_doc_id"]
        if doc_id is not None:
            doc = db.query(UserDocument).filter(UserDocument.id == doc_id,
                                                UserDocument.user_id == current_user.id).first()
            if doc is None:
                raise HTTPException(status_code=404, detail="Document not found")
            for q in app.form_schema_snapshot or []:
                entry = (app.answers or {}).get(q["id"])
                if q.get("category") == "resume" and q.get("type") == "file" and entry and entry.get("source") != "user":
                    answers = dict(app.answers)
                    answers[q["id"]] = {"value": doc.filename, "source": "profile", "confirmed": True, "needs_user": False}
                    app.answers = answers
        app.resume_doc_id = doc_id
        changes.append("resume")
    if "cover_letter_text" in data:
        app.cover_letter_text = data["cover_letter_text"] or None
        changes.append("cover letter")
    if changes:
        app.updated_at = svc.utcnow()
        svc.add_event(db, app, "updated", "Updated " + " and ".join(changes), {"fields": list(data)})
        db.commit()
    return _detail(db, app, current_user)


@router.post("/applications/{app_id}/approve")
def approve_application(app_id: int, current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    app = _get_app(db, current_user, app_id)
    blocked = _require_plan(db, current_user)
    if blocked:
        return blocked
    if app.status == "approved":
        return _detail(db, app, current_user)
    if app.status not in ("needs_input", "ready_for_review"):
        raise _conflict(f"Can't approve an application that is {app.status}")
    prefs = svc.get_preferences(db, current_user)
    missing = svc.needs_user_ids(app)
    if prefs.mode != "auto":
        missing += [q for q in svc.unconfirmed_draft_ids(app) if q not in missing]
    if missing:
        return JSONResponse(status_code=400, content={
            "detail": "Answer or confirm the highlighted questions before approving", "missing": missing})
    svc.transition(db, app, "approved", "approved", "Approved by you")
    db.commit()
    return _detail(db, app, current_user)


@router.post("/applications/{app_id}/handoff")
def handoff_application(app_id: int, current_user: User = Depends(get_current_user),
                        db: Session = Depends(get_db)):
    app = _get_app(db, current_user, app_id)
    blocked = _require_plan(db, current_user)
    if blocked:
        return blocked
    if app.status not in ("approved", "handed_off"):
        raise _conflict("Only approved applications can be handed off")
    if app.status == "approved":
        svc.transition(db, app, "handed_off", "handed_off", "Opened the application to submit")
        db.commit()
    return svc.handoff_payload(app)


@router.post("/applications/{app_id}/mark-submitted")
def mark_submitted(app_id: int, body: Optional[MarkSubmitted] = None,
                   current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = _get_app(db, current_user, app_id)
    if app.status == "submitted":
        return _detail(db, app, current_user)
    try:
        app.submitted_via = "manual"
        app.confirmation = (body.confirmation if body else None) or app.confirmation
        svc.transition(db, app, "submitted", "submitted", "Marked as submitted by you",
                       {"confirmation": app.confirmation})
    except svc.TransitionError as e:
        db.rollback()
        raise _conflict(str(e))
    db.commit()
    return _detail(db, app, current_user)


@router.post("/applications/{app_id}/skip")
def skip_application(app_id: int, body: Optional[SkipIn] = None, current_user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    app = _get_app(db, current_user, app_id)
    if app.status == "skipped":
        return _detail(db, app, current_user)
    try:
        svc.transition(db, app, "skipped", "skipped", (body.reason if body and body.reason else "Skipped by you"))
    except svc.TransitionError as e:
        raise _conflict(str(e))
    db.commit()
    return _detail(db, app, current_user)


@router.post("/applications/{app_id}/retry-draft")
def retry_draft(app_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = _get_app(db, current_user, app_id)
    blocked = _require_plan(db, current_user)
    if blocked:
        return blocked
    if app.status in ("submitted", "confirmed", "withdrawn", "handed_off"):
        raise _conflict(f"Can't re-draft an application that is {app.status}")
    svc.draft_application(db, app, current_user, force_schema=True, allow_auto_approve=False)
    return _detail(db, app, current_user)


# --------------------------------------------------------------------------- answer bank

def _bank_item(row: AnswerBankEntry) -> Dict[str, Any]:
    return {"id": row.id, "question_key": row.question_key, "label": row.label, "value": row.value,
            "sensitive": bool(row.sensitive)}


@router.get("/answer-bank")
def list_bank(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = (db.query(AnswerBankEntry).filter(AnswerBankEntry.user_id == current_user.id)
            .order_by(AnswerBankEntry.label.asc()).all())
    return {"items": [_bank_item(r) for r in rows]}


@router.post("/answer-bank", status_code=201)
def create_bank(body: BankIn, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not normalize_question_key(body.label):
        raise HTTPException(status_code=400, detail="Label must contain letters or numbers")
    row = svc.upsert_bank(db, current_user, body.label, body.value, body.sensitive)
    db.commit()
    return _bank_item(row)


@router.put("/answer-bank/{entry_id}")
def update_bank(entry_id: int, body: BankUpdate, current_user: User = Depends(get_current_user),
                db: Session = Depends(get_db)):
    row = db.query(AnswerBankEntry).filter(AnswerBankEntry.id == entry_id,
                                           AnswerBankEntry.user_id == current_user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Answer not found")
    data = body.model_dump(exclude_unset=True)
    if data.get("label"):
        key = normalize_question_key(data["label"])
        clash = db.query(AnswerBankEntry).filter(AnswerBankEntry.user_id == current_user.id,
                                                 AnswerBankEntry.question_key == key,
                                                 AnswerBankEntry.id != row.id).first()
        if clash:
            raise _conflict("Another saved answer already uses this question")
        row.label, row.question_key = data["label"].strip(), key
    if "value" in data and data["value"] is not None:
        row.value = data["value"]
    if data.get("sensitive") is not None:
        row.sensitive = bool(data["sensitive"])
    row.updated_at = svc.utcnow()
    db.commit()
    return _bank_item(row)


@router.delete("/answer-bank/{entry_id}")
def delete_bank(entry_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.query(AnswerBankEntry).filter(AnswerBankEntry.id == entry_id,
                                           AnswerBankEntry.user_id == current_user.id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Answer not found")
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": entry_id}


# --------------------------------------------------------------------------- stats

@router.get("/stats")
def get_stats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from sqlalchemy import func

    prefs = svc.get_preferences(db, current_user)
    plan = svc.plan_for(db, current_user, prefs)
    rows = (db.query(Application.status, func.count(Application.id))
            .filter(Application.user_id == current_user.id).group_by(Application.status).all())
    return {
        "today_count": svc.today_count(db, current_user.id),
        "daily_cap": svc.effective_daily_cap(prefs, plan),
        "by_status": {status: count for status, count in rows},
    }


# --------------------------------------------------------------------------- extension (Phase 2 placeholders)

@router.get("/extension/next")
def extension_next(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """The oldest approved application, with its prefill payload. Does not change status."""
    app = (db.query(Application).options(joinedload(Application.job).joinedload(Job.company))
           .filter(Application.user_id == current_user.id, Application.status == "approved")
           .order_by(Application.approved_at.asc().nullslast(), Application.id.asc()).first())
    if app is None:
        return {"application": None}
    detail = svc.application_detail(db, app, current_user)
    detail.update(svc.handoff_payload(app))
    return {"application": detail}


@router.post("/applications/{app_id}/extension-result")
def extension_result(app_id: int, body: ExtensionResult, current_user: User = Depends(get_current_user),
                     db: Session = Depends(get_db)):
    app = _get_app(db, current_user, app_id)
    try:
        if body.status == "submitted":
            if app.status == "approved":
                svc.transition(db, app, "handed_off", "handed_off", "Opened by the Cariara extension")
            app.submitted_via = "extension"
            app.confirmation = body.confirmation or app.confirmation
            svc.transition(db, app, "submitted", "extension_submitted", "Submitted from your browser",
                           {"confirmation": body.confirmation})
        elif body.status == "failed":
            svc.transition(db, app, "failed", "extension_failed", body.error or "The extension could not submit",
                           {"error": body.error})
        else:  # captcha: the customer finishes in their own browser; we never solve it
            if app.status == "approved":
                svc.transition(db, app, "handed_off", "handed_off", "Opened by the Cariara extension")
            svc.add_event(db, app, "extension_captcha",
                          "The site asked for a CAPTCHA - finish the application in your browser",
                          {"error": body.error})
    except svc.TransitionError as e:
        db.rollback()
        raise _conflict(str(e))
    db.commit()
    return _detail(db, app, current_user)
