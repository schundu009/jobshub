"""
Admin › Settings › Data: deleting old jobs and removing duplicates.

Both only ever delete scraped postings that nobody has touched:
- never a job a user added (jobs.user_id),
- never a job with user activity: an application, the apply queue, a
  submission, an interview, a note or a document (USER_LINKS).

Old jobs: listed (effective_posted_at, else posted_date, else first_seen_at,
else created_at) more than N days ago. A posting a scrape still lists (active
and seen in the last STILL_LISTED_DAYS) is kept unless include_open.

Duplicates: the same job_url, or the same company + title + location with
the same description (different openings often share a title, so a title
alone is not a duplicate). The copy kept is the one with user activity, else
the open one, else the most recently seen, else the oldest.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

from sqlalchemy import and_, exists, func, or_, select

from models import Application, ApplicationSubmission, ApplyQueueItem, Document, Interview, Job, Note

STILL_LISTED_DAYS = 2
DELETE_BATCH = 1000

# Rows that mean a person used the job; jobs with any are never deleted.
USER_LINKS = (Application, ApplyQueueItem, ApplicationSubmission, Interview, Note, Document)


def _listed_at():
    return func.coalesce(Job.effective_posted_at, Job.posted_date, Job.first_seen_at, Job.created_at)


def _has_user_link():
    return or_(*[exists().where(model.job_id == Job.id) for model in USER_LINKS])


def _still_listed(now: datetime):
    seen_cutoff = now - timedelta(days=STILL_LISTED_DAYS)
    return and_(Job.is_active.is_(True), func.coalesce(Job.last_seen_at, Job.updated_at) >= seen_cutoff)


def _delete_ids(db, ids: list[int]) -> int:
    """Delete jobs in batches; their scores and form schemas cascade."""
    deleted = 0
    for i in range(0, len(ids), DELETE_BATCH):
        chunk = ids[i:i + DELETE_BATCH]
        deleted += db.query(Job).filter(Job.id.in_(chunk)).delete(synchronize_session=False)
        db.commit()
    return deleted


def old_jobs(db, days: int, include_open: bool = False, apply: bool = False, now: datetime | None = None) -> dict:
    """Counts of jobs listed more than `days` ago; deletes the deletable ones when apply."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=days)
    old = _listed_at() < cutoff

    user_added = db.query(func.count(Job.id)).filter(old, Job.user_id.isnot(None)).scalar() or 0
    scraped = db.query(Job.id).filter(old, Job.user_id.is_(None))
    linked = scraped.filter(_has_user_link()).count()
    unlinked = scraped.filter(~_has_user_link())
    still_open = unlinked.filter(_still_listed(now)).count()
    deletable_q = unlinked if include_open else unlinked.filter(~_still_listed(now))
    ids = [row[0] for row in deletable_q.all()]

    result = {
        "cutoff_date": cutoff.isoformat(),
        "dry_run": not apply,
        "include_open": include_open,
        "jobs_count": len(ids),
        "kept_still_open": 0 if include_open else still_open,
        "kept_with_user_activity": linked,
        "kept_user_added": user_added,
        "still_open_included": still_open if include_open else 0,
    }
    if apply and ids:
        result["deleted"] = _delete_ids(db, ids)
    return result


def _norm(text: str | None) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip().lower()


def _keeper_rank(job: Job, linked_ids: set[int], now: datetime):
    """Lower sorts first: the copy to keep."""
    seen = job.last_seen_at or job.updated_at
    is_open = bool(job.is_active) and seen is not None and seen >= now - timedelta(days=STILL_LISTED_DAYS)
    return (job.id not in linked_ids, not is_open, -(seen.timestamp() if seen else 0), job.id)


def duplicates(db, apply: bool = False, now: datetime | None = None) -> dict:
    """Duplicate scraped jobs by URL, or by company + title + location + description."""
    now = now or datetime.utcnow()
    scraped = Job.user_id.is_(None)

    url_groups = select(Job.job_url).where(scraped, Job.job_url.isnot(None), Job.job_url != '') \
        .group_by(Job.job_url).having(func.count(Job.id) > 1)
    title_groups = select(Job.company_id, Job.title, func.coalesce(Job.location, '')).where(
        scraped, Job.title.isnot(None), Job.title != '',
    ).group_by(Job.company_id, Job.title, func.coalesce(Job.location, '')).having(func.count(Job.id) > 1)

    groups: list[list[Job]] = []
    url_keys = [r[0] for r in db.execute(url_groups).all()]
    for i in range(0, len(url_keys), 500):
        rows = db.query(Job).filter(scraped, Job.job_url.in_(url_keys[i:i + 500])).all()
        by_url: dict[str, list[Job]] = {}
        for j in rows:
            by_url.setdefault(j.job_url, []).append(j)
        groups.extend(by_url.values())
    by_url_count = sum(len(g) - 1 for g in groups)
    in_url_group = {j.id for g in groups for j in g}

    title_count = 0
    for company_id, title, location in db.execute(title_groups).all():
        rows = db.query(Job).filter(
            scraped, Job.company_id == company_id, Job.title == title,
            func.coalesce(Job.location, '') == location,
        ).all()
        by_text: dict[str, list[Job]] = {}
        for j in rows:
            if j.id in in_url_group:
                continue  # already handled as a same-URL copy
            text = _norm(j.job_description)
            if len(text) >= 200:  # thin or missing text can't prove two postings are one
                by_text.setdefault(text, []).append(j)
        for same in by_text.values():
            if len(same) > 1:
                groups.append(same)
                title_count += len(same) - 1

    id_list = list({j.id for g in groups for j in g})
    linked_ids: set[int] = set()
    for i in range(0, len(id_list), 500):
        chunk = id_list[i:i + 500]
        for model in USER_LINKS:
            linked_ids.update(r[0] for r in db.query(model.job_id).filter(model.job_id.in_(chunk)).all())

    to_delete: set[int] = set()
    kept_linked = 0
    for group in groups:
        group = sorted(group, key=lambda j: _keeper_rank(j, linked_ids, now))
        for j in group[1:]:
            if j.id in linked_ids:
                kept_linked += 1  # a second copy someone used stays
            else:
                to_delete.add(j.id)

    result = {
        "dry_run": not apply,
        "duplicates_count": len(to_delete),
        "by_url": by_url_count,
        "by_title_and_description": title_count,
        "kept_with_user_activity": kept_linked,
    }
    if apply and to_delete:
        result["deleted"] = _delete_ids(db, sorted(to_delete))
    return result
