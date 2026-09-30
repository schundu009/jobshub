"""
Celery tasks for Cariara Auto Apply (queue: default).

- refresh_queue_for_user(user_id): rebuild one user's match queue (on demand)
- nightly_matching(): rebuild queues for every user with Auto Apply enabled
- prepare_for_user(user_id): auto mode - draft applications up to the daily cap
- prepare_auto_applications(): hourly fan-out of prepare_for_user

None of these submit an application: prepared applications wait for the
customer (review mode) or are auto-approved for the browser extension (auto mode).
"""
import logging

from celery_app import celery_app
from database import SessionLocal
from models import ApplyPreference, User

logger = logging.getLogger(__name__)


def get_db():
    return SessionLocal()


def build_queue_for(db, user) -> int:
    from services.apply import matching
    from services.apply import service as svc

    prefs = svc.get_preferences(db, user)
    resume = svc.default_resume(db, user)
    return matching.build_queue(db, user, prefs, (resume.content_text or "") if resume else "")


def refresh_queue_for_user_sync(user_id: int) -> dict:
    db = get_db()
    try:
        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
        if not user:
            return {"status": "skipped", "reason": "no_user"}
        count = build_queue_for(db, user)
        return {"status": "ok", "items": count}
    finally:
        db.close()


@celery_app.task
def refresh_queue_for_user(user_id: int) -> dict:
    result = refresh_queue_for_user_sync(user_id)
    prepare_for_user_sync(user_id)  # auto mode: act on the fresh queue
    return result


def _enabled_user_ids(db, auto_only: bool = False):
    query = db.query(ApplyPreference.user_id).filter(ApplyPreference.enabled == True)  # noqa: E712
    if auto_only:
        query = query.filter(ApplyPreference.mode == "auto")
    return [row[0] for row in query.all()]


@celery_app.task
def nightly_matching() -> dict:
    db = get_db()
    try:
        user_ids = _enabled_user_ids(db)
    finally:
        db.close()
    done = 0
    for user_id in user_ids:
        try:
            refresh_queue_for_user_sync(user_id)
            done += 1
        except Exception as e:
            logger.warning("nightly matching failed for user %s: %s", user_id, e)
    return {"users": len(user_ids), "refreshed": done}


def prepare_for_user_sync(user_id: int, ai_drafter=None) -> dict:
    from services.apply import service as svc

    db = get_db()
    try:
        user = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
        if not user:
            return {"created": 0, "reason": "no_user"}
        return svc.prepare_auto_for_user(db, user, ai_drafter=ai_drafter)
    finally:
        db.close()


@celery_app.task
def prepare_for_user(user_id: int) -> dict:
    return prepare_for_user_sync(user_id)


@celery_app.task
def prepare_auto_applications() -> dict:
    db = get_db()
    try:
        user_ids = _enabled_user_ids(db, auto_only=True)
    finally:
        db.close()
    for user_id in user_ids:
        prepare_for_user.delay(user_id)
    return {"users": len(user_ids)}
