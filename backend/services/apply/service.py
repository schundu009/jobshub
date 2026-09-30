"""
Auto Apply application lifecycle: preferences, profile, drafting, status
machine, events and serialization. Routes and Celery tasks share this module.
"""
import logging
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import (
    AnswerBankEntry, Application, ApplicationEvent, ApplyPreference, ApplyProfile,
    ApplyQueueItem, Job, User, UserDocument,
)
from services.apply import form_schema
from services.apply.constants import (
    ALLOWED_TRANSITIONS, DEFAULT_DAILY_CAP, DEFAULT_MIN_MATCH_SCORE, SUPPORTED_ATS,
)
from services.apply.matching import is_stale_for_apply
from services.apply.plans import PlanInfo, resolve_plan
from services.apply.resolver import (
    AnswerResolver, JobContext, ProfileView, normalize_question_key,
)

logger = logging.getLogger(__name__)


class TransitionError(Exception):
    pass


# --------------------------------------------------------------------------- helpers

def utcnow() -> datetime:
    return datetime.utcnow()


def today_start() -> datetime:
    now = utcnow()
    return datetime(now.year, now.month, now.day)


def next_reset() -> datetime:
    return today_start() + timedelta(days=1)


def _to_bool(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    low = str(value).strip().lower()
    if low in ("yes", "true", "1", "y"):
        return True
    if low in ("no", "false", "0", "n"):
        return False
    return None


def _from_bool(value: Optional[bool]) -> Optional[str]:
    if value is None:
        return None
    return "yes" if value else "no"


# --------------------------------------------------------------------------- preferences

def get_preferences(db: Session, user: User, create: bool = True) -> Optional[ApplyPreference]:
    prefs = db.query(ApplyPreference).filter(ApplyPreference.user_id == user.id).first()
    if prefs is None and create:
        # Seed from the settings the user already gave us.
        prefs = ApplyPreference(
            user_id=user.id,
            enabled=False,
            mode="review",
            min_match_score=DEFAULT_MIN_MATCH_SCORE,
            daily_cap=DEFAULT_DAILY_CAP,
            target_roles=[t for t in (user.job_titles or []) if t][:10],
            locations=[c for c in (user.preferred_cities or user.preferred_locations or []) if c][:20],
            remote_ok=True if user.remote_ok is None else bool(user.remote_ok),
            salary_floor=user.min_salary,
            excluded_companies=list(user.excluded_companies or []),
            ats_allowlist=list(SUPPORTED_ATS),
        )
        db.add(prefs)
        try:
            db.commit()
        except IntegrityError:
            # A parallel first request created the row; use that one.
            db.rollback()
            return db.query(ApplyPreference).filter(ApplyPreference.user_id == user.id).first()
        db.refresh(prefs)
    return prefs


def plan_for(db: Session, user: User, prefs: Optional[ApplyPreference] = None) -> PlanInfo:
    prefs = prefs or get_preferences(db, user)
    return resolve_plan(user, prefs.plan_override if prefs else None)


def effective_daily_cap(prefs: ApplyPreference, plan: PlanInfo) -> int:
    if not plan.plan_ok:
        return 0
    return max(0, min(int(prefs.daily_cap or DEFAULT_DAILY_CAP), plan.daily_cap_max))


def preferences_payload(prefs: ApplyPreference, plan: PlanInfo) -> Dict[str, Any]:
    return {
        "enabled": bool(prefs.enabled),
        "mode": prefs.mode or "review",
        "min_match_score": int(prefs.min_match_score if prefs.min_match_score is not None else DEFAULT_MIN_MATCH_SCORE),
        "daily_cap": int(prefs.daily_cap or DEFAULT_DAILY_CAP),
        "daily_cap_max": plan.daily_cap_max,
        "target_roles": list(prefs.target_roles or []),
        "locations": list(prefs.locations or []),
        "remote_ok": bool(prefs.remote_ok),
        "salary_floor": prefs.salary_floor,
        "excluded_companies": list(prefs.excluded_companies or []),
        "ats_allowlist": list(prefs.ats_allowlist or []),
        "plan_ok": plan.plan_ok,
    }


# --------------------------------------------------------------------------- profile

def get_apply_profile(db: Session, user: User) -> ApplyProfile:
    row = db.query(ApplyProfile).filter(ApplyProfile.user_id == user.id).first()
    if row is None:
        row = ApplyProfile(user_id=user.id, eeo_opt_in=False)
        db.add(row)
        try:
            with db.begin_nested():
                db.flush()
        except IntegrityError:
            # A parallel first request created the row; use that one.
            row = db.query(ApplyProfile).filter(ApplyProfile.user_id == user.id).first()
    return row


def profile_payload(user: User, ap: ApplyProfile) -> Dict[str, Any]:
    return {
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.resume_email or user.email,
        "phone": user.phone,
        "location": {"city": user.city, "state": user.state, "country": user.address_country or user.country},
        "linkedin": user.linkedin_url,
        "github": user.github_url,
        "portfolio": user.portfolio_url,
        "work_authorized_us": _to_bool(user.us_authorized),
        "requires_sponsorship": _to_bool(user.requires_sponsorship),
        "willing_to_relocate": _to_bool(user.willing_to_relocate),
        "earliest_start_date": user.available_date.isoformat() if user.available_date else None,
        "salary_expectation": ap.salary_expectation,
        "notice_period": ap.notice_period,
        "eeo": {
            "opt_in": bool(ap.eeo_opt_in),
            "gender": user.gender,
            "race": user.ethnicity,
            "veteran": user.veteran_status,
            "disability": user.disability_status,
        },
    }


def update_profile(db: Session, user: User, data: Dict[str, Any]) -> None:
    ap = get_apply_profile(db, user)
    simple = {
        "first_name": "first_name", "last_name": "last_name", "phone": "phone",
        "linkedin": "linkedin_url", "github": "github_url", "portfolio": "portfolio_url",
    }
    for key, attr in simple.items():
        if key in data:
            setattr(user, attr, data[key] or None)
    if "email" in data:
        # The login email never changes here; this is the address used on applications.
        user.resume_email = data["email"] or None
    if "location" in data and data["location"] is not None:
        loc = data["location"]
        for key, attr in (("city", "city"), ("state", "state"), ("country", "address_country")):
            if key in loc:
                setattr(user, attr, loc[key] or None)
    for key, attr in (("work_authorized_us", "us_authorized"), ("requires_sponsorship", "requires_sponsorship"),
                      ("willing_to_relocate", "willing_to_relocate")):
        if key in data:
            setattr(user, attr, _from_bool(data[key]))
    if "earliest_start_date" in data:
        value = data["earliest_start_date"]
        user.available_date = date.fromisoformat(value) if value else None
    if "salary_expectation" in data:
        ap.salary_expectation = data["salary_expectation"] or None
    if "notice_period" in data:
        ap.notice_period = data["notice_period"] or None
    if "eeo" in data and data["eeo"] is not None:
        eeo = data["eeo"]
        if "opt_in" in eeo and eeo["opt_in"] is not None:
            ap.eeo_opt_in = bool(eeo["opt_in"])
        for key, attr in (("gender", "gender"), ("race", "ethnicity"), ("veteran", "veteran_status"),
                          ("disability", "disability_status")):
            if key in eeo:
                setattr(user, attr, eeo[key] or None)
    db.commit()


# --------------------------------------------------------------------------- documents

def resume_documents(db: Session, user: User) -> List[UserDocument]:
    return (db.query(UserDocument)
            .filter(UserDocument.user_id == user.id, UserDocument.document_type == "resume")
            .order_by(UserDocument.is_default.desc(), UserDocument.updated_at.desc(), UserDocument.id.desc())
            .all())


def default_resume(db: Session, user: User) -> Optional[UserDocument]:
    docs = resume_documents(db, user)
    if user.base_resume_id:
        for doc in docs:
            if doc.id == user.base_resume_id:
                return doc
    for doc in docs:
        if (doc.content_text or "").strip():
            return doc
    return docs[0] if docs else None


# --------------------------------------------------------------------------- readiness

READINESS_FIELDS = [
    ("first_name", "First name"),
    ("last_name", "Last name"),
    ("email", "Email"),
    ("phone", "Phone"),
    ("work_authorized_us", "Work authorization (US)"),
    ("requires_sponsorship", "Visa sponsorship"),
]


def readiness(db: Session, user: User) -> Dict[str, Any]:
    prefs = get_preferences(db, user)
    plan = plan_for(db, user, prefs)
    profile = profile_payload(user, get_apply_profile(db, user))
    missing = [{"field": f, "label": label} for f, label in READINESS_FIELDS if profile.get(f) in (None, "")]
    resume = default_resume(db, user)
    resume_ok = bool(resume and (resume.content_text or "").strip())
    db.commit()
    return {"ready": plan.plan_ok and resume_ok and not missing, "plan_ok": plan.plan_ok,
            "resume_ok": resume_ok, "missing": missing}


# --------------------------------------------------------------------------- events & transitions

def add_event(db: Session, app: Application, type_: str, message: Optional[str] = None,
              data: Optional[Dict[str, Any]] = None) -> ApplicationEvent:
    event = ApplicationEvent(application_id=app.id, type=type_, message=message, data=data or {},
                             created_at=utcnow())
    db.add(event)
    return event


def transition(db: Session, app: Application, new_status: str, event_type: Optional[str] = None,
               message: Optional[str] = None, data: Optional[Dict[str, Any]] = None) -> None:
    old = app.status
    if new_status != old and new_status not in ALLOWED_TRANSITIONS.get(old, set()):
        raise TransitionError(f"Cannot move application from {old} to {new_status}")
    app.status = new_status
    app.updated_at = utcnow()
    if new_status == "approved":
        app.approved_at = utcnow()
    if new_status == "submitted":
        app.submitted_at = utcnow()
    payload = {"from": old, "to": new_status}
    payload.update(data or {})
    add_event(db, app, event_type or new_status, message, payload)


# --------------------------------------------------------------------------- drafting

def build_profile_view(db: Session, user: User, resume: Optional[UserDocument]) -> ProfileView:
    ap = get_apply_profile(db, user)
    bank = {row.question_key: row.value for row in
            db.query(AnswerBankEntry).filter(AnswerBankEntry.user_id == user.id).all()}
    return ProfileView(
        first_name=user.first_name, last_name=user.last_name, preferred_name=user.preferred_name,
        email=user.resume_email or user.email, phone=user.phone,
        city=user.city, state=user.state, country=user.address_country or user.country,
        address_line1=user.address_line1, postal_code=user.postal_code,
        linkedin=user.linkedin_url, github=user.github_url, portfolio=user.portfolio_url,
        twitter=user.twitter_url,
        work_authorized_us=_to_bool(user.us_authorized),
        requires_sponsorship=_to_bool(user.requires_sponsorship),
        willing_to_relocate=_to_bool(user.willing_to_relocate),
        earliest_start_date=user.available_date.isoformat() if user.available_date else None,
        salary_expectation=ap.salary_expectation, notice_period=ap.notice_period,
        eeo_opt_in=bool(ap.eeo_opt_in),
        gender=user.gender, race=user.ethnicity, veteran=user.veteran_status, disability=user.disability_status,
        resume_filename=resume.filename if resume else None,
        resume_text=(resume.content_text or None) if resume else None,
        bank=bank,
    )


def job_context(job: Job) -> JobContext:
    from routes.jobs import plain_text_description

    return JobContext(
        title=job.title or "",
        company=(job.company.name if job.company else "") or "",
        description=plain_text_description(job.job_description or "") or "",
    )


def needs_user_ids(app: Application) -> List[str]:
    return [qid for qid, a in (app.answers or {}).items() if a.get("needs_user")]


def unconfirmed_draft_ids(app: Application) -> List[str]:
    return [qid for qid, a in (app.answers or {}).items()
            if a.get("source") == "ai_draft" and not a.get("confirmed")]


def status_after_answers(app: Application) -> str:
    return "needs_input" if needs_user_ids(app) else "ready_for_review"


def draft_application(db: Session, app: Application, user: User, force_schema: bool = False,
                      ai_drafter=None, allow_auto_approve: bool = True) -> Application:
    """(Re)build schema + answers. Moves the application out of drafting."""
    if app.status != "drafting":
        transition(db, app, "drafting", "drafting", "Preparing application")
    job = db.query(Job).filter(Job.id == app.job_id).first()
    result = form_schema.get_form_schema(db, job, force=force_schema)
    app.ats = result.ats
    app.apply_url = result.apply_url or (job.job_url if job else None)

    if not result.supported:
        transition(db, app, "unsupported", "unsupported",
                   "This job's application site isn't supported yet; apply manually with the link.",
                   {"ats": result.ats})
        db.commit()
        return app
    if result.error:
        transition(db, app, "failed", "draft_failed", result.error, {"closed": result.closed})
        db.commit()
        return app

    resume = None
    if app.resume_doc_id:
        resume = db.query(UserDocument).filter(UserDocument.id == app.resume_doc_id,
                                               UserDocument.user_id == user.id).first()
    if resume is None:
        resume = default_resume(db, user)
        app.resume_doc_id = resume.id if resume else None

    resolver = AnswerResolver(build_profile_view(db, user, resume), job_context(job),
                              ai_drafter=ai_drafter, cover_letter_text=app.cover_letter_text)
    app.form_schema_snapshot = result.questions
    app.answers = resolver.resolve(result.questions, existing=app.answers or {})

    prefs = get_preferences(db, user)
    status = status_after_answers(app)
    counts = {"questions": len(result.questions), "needs_user": len(needs_user_ids(app)),
              "ai_drafts": len(unconfirmed_draft_ids(app))}
    if status == "ready_for_review" and allow_auto_approve and prefs.enabled and prefs.mode == "auto" \
            and plan_for(db, user, prefs).plan_ok:
        transition(db, app, "approved", "auto_approved",
                   "Auto mode: all answers resolved, approved automatically", counts)
    else:
        transition(db, app, status, status,
                   "Needs your input" if status == "needs_input" else "Ready for your review", counts)
    db.commit()
    return app


# --------------------------------------------------------------------------- creation & caps

def today_count(db: Session, user_id: int) -> int:
    return (db.query(func.count(Application.id))
            .filter(Application.user_id == user_id, Application.created_at >= today_start())
            .scalar() or 0)


def _score_now(db: Session, user: User, job: Job) -> Optional[int]:
    """Match score for a job that is not in the user's queue (ignores hard filters)."""
    try:
        from services.apply import matching

        prefs = get_preferences(db, user)
        resume = default_resume(db, user)
        ctx = matching.MatchContext(user, prefs, (resume.content_text or "") if resume else "")
        ctx.excluded, ctx.allowlist, ctx.locations, ctx.salary_floor = [], set(), [], None
        result = matching.score_job(job, ctx)
        return result[0] if result else None
    except Exception as e:
        logger.debug("match score failed for job %s: %s", job.id, e)
        return None


def create_application(db: Session, user: User, job: Job, created_by: str = "user",
                       match_score: Optional[int] = None, ai_drafter=None) -> Application:
    if match_score is None:
        item = db.query(ApplyQueueItem).filter(ApplyQueueItem.user_id == user.id,
                                               ApplyQueueItem.job_id == job.id).first()
        match_score = item.match_score if item else _score_now(db, user, job)
    now = utcnow()
    app = Application(user_id=user.id, job_id=job.id, status="drafting", answers={},
                      form_schema_snapshot=[], match_score=match_score, created_by=created_by,
                      created_at=now, updated_at=now)
    db.add(app)
    db.flush()
    add_event(db, app, "created", "Created from your match queue" if created_by == "auto" else "Application created",
              {"created_by": created_by, "match_score": match_score})
    db.commit()
    return draft_application(db, app, user, ai_drafter=ai_drafter)


# --------------------------------------------------------------------------- answers

def apply_user_answers(db: Session, app: Application, user: User, answers: Dict[str, Any],
                       save_to_bank: bool = False) -> List[str]:
    """Set answers from the customer. Returns unknown question ids (nothing applied if any)."""
    schema = {q["id"]: q for q in (app.form_schema_snapshot or [])}
    unknown = [qid for qid in answers if qid not in schema]
    if unknown:
        return unknown
    current = dict(app.answers or {})
    for qid, value in answers.items():
        q = schema[qid]
        empty = value is None or value == "" or value == []
        current[qid] = {"value": None if empty else value, "source": None if empty else "user",
                        "confirmed": not empty, "needs_user": bool(empty and q.get("required"))}
        if save_to_bank and not empty and q.get("category") == "custom" and q.get("type") != "file":
            upsert_bank(db, user, q["label"], value if isinstance(value, str) else ", ".join(map(str, value))
                        if isinstance(value, list) else str(value))
    app.answers = current
    new_status = status_after_answers(app)
    transition(db, app, new_status, "answers_updated", f"{len(answers)} answer(s) updated",
               {"question_ids": list(answers)})
    db.commit()
    return []


def upsert_bank(db: Session, user: User, label: str, value: str, sensitive: Optional[bool] = None) -> AnswerBankEntry:
    key = normalize_question_key(label)
    row = db.query(AnswerBankEntry).filter(AnswerBankEntry.user_id == user.id,
                                           AnswerBankEntry.question_key == key).first()
    if row is None:
        row = AnswerBankEntry(user_id=user.id, question_key=key, label=label.strip(), value=value,
                              sensitive=bool(sensitive))
        db.add(row)
    else:
        row.label = label.strip()
        row.value = value
        if sensitive is not None:
            row.sensitive = bool(sensitive)
        row.updated_at = utcnow()
    db.flush()
    return row


# --------------------------------------------------------------------------- serialization

def job_payload(job: Optional[Job], ats: Optional[str] = None, full: bool = True) -> Dict[str, Any]:
    if job is None:
        return {"id": None, "title": None, "company_name": None, "location": None}
    data = {
        "id": job.id,
        "title": job.title,
        "company_name": job.company.name if job.company else None,
        "location": job.location,
    }
    if full:
        data.update({
            "job_url": job.job_url,
            "posted_date": job.posted_date.isoformat() if job.posted_date else None,
            "ats": ats,
        })
    return data


def _iso(value: Optional[datetime]) -> Optional[str]:
    # Stored as naive UTC; say so, or browsers read it as local time.
    if not value:
        return None
    text = value.isoformat()
    return text if value.tzinfo else text + "Z"



def questions_payload(app: Application) -> List[Dict[str, Any]]:
    out = []
    answers = app.answers or {}
    for q in app.form_schema_snapshot or []:
        a = answers.get(q["id"]) or {}
        out.append({
            "id": q["id"], "label": q["label"], "type": q["type"], "required": bool(q.get("required")),
            "options": q.get("options") or [], "category": q.get("category"),
            "description": q.get("description"),
            "answer": a.get("value"), "source": a.get("source"),
            "confirmed": bool(a.get("confirmed")), "needs_user": bool(a.get("needs_user")),
        })
    return out


def application_summary(app: Application) -> Dict[str, Any]:
    return {
        "id": app.id,
        "status": app.status,
        "job": job_payload(app.job, full=False),
        "ats": app.ats,
        "match_score": app.match_score,
        "needs_user_count": len(needs_user_ids(app)),
        "updated_at": _iso(app.updated_at),
    }


def application_detail(db: Session, app: Application, user: User) -> Dict[str, Any]:
    events = (db.query(ApplicationEvent).filter(ApplicationEvent.application_id == app.id)
              .order_by(ApplicationEvent.id.asc()).all())
    return {
        "id": app.id,
        "status": app.status,
        "ats": app.ats,
        "apply_url": app.apply_url,
        "match_score": app.match_score,
        "job": job_payload(app.job, app.ats),
        "questions": questions_payload(app),
        "resume_doc_id": app.resume_doc_id,
        "documents": [{"id": d.id, "filename": d.filename} for d in resume_documents(db, user)],
        "cover_letter_text": app.cover_letter_text,
        "events": [{"type": e.type, "message": e.message, "created_at": _iso(e.created_at)} for e in events],
        "created_at": _iso(app.created_at),
        "updated_at": _iso(app.updated_at),
        "approved_at": _iso(app.approved_at),
        "submitted_at": _iso(app.submitted_at),
        "submitted_via": app.submitted_via,
        "confirmation": app.confirmation,
    }


def handoff_payload(app: Application) -> Dict[str, Any]:
    prefill = []
    answers = app.answers or {}
    for q in app.form_schema_snapshot or []:
        value = (answers.get(q["id"]) or {}).get("value")
        if value in (None, "", []):
            continue
        prefill.append({"question_id": q["id"], "label": q["label"], "value": value,
                        "type": q.get("type"), "category": q.get("category")})
    return {"apply_url": app.apply_url, "prefill": prefill, "cover_letter_text": app.cover_letter_text}


# --------------------------------------------------------------------------- auto mode

def prepare_auto_for_user(db: Session, user: User, ai_drafter=None) -> Dict[str, Any]:
    """Create applications from the queue for an auto-mode user, up to today's remaining cap."""
    prefs = get_preferences(db, user)
    if not prefs.enabled or prefs.mode != "auto":
        return {"created": 0, "reason": "not_auto"}
    plan = plan_for(db, user, prefs)
    if not plan.plan_ok:
        return {"created": 0, "reason": "plan"}
    remaining = effective_daily_cap(prefs, plan) - today_count(db, user.id)
    if remaining <= 0:
        return {"created": 0, "reason": "cap"}

    applied = db.query(Application.job_id).filter(Application.user_id == user.id)
    items = (db.query(ApplyQueueItem)
             .filter(ApplyQueueItem.user_id == user.id,
                     ApplyQueueItem.match_score >= int(prefs.min_match_score or DEFAULT_MIN_MATCH_SCORE),
                     ~ApplyQueueItem.job_id.in_(applied))
             .order_by(ApplyQueueItem.match_score.desc(), ApplyQueueItem.id.asc())
             .limit(remaining).all())
    created = []
    for item in items:
        job = db.query(Job).filter(Job.id == item.job_id).first()
        if not job or not job.is_active or is_stale_for_apply(job):
            continue
        try:
            app = create_application(db, user, job, created_by="auto", match_score=item.match_score,
                                     ai_drafter=ai_drafter)
            created.append(app.id)
        except Exception as e:  # one bad job must not stop the batch
            db.rollback()
            logger.warning("auto prepare failed for user %s job %s: %s", user.id, item.job_id, e)
    return {"created": len(created), "application_ids": created}
