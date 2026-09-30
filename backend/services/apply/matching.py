"""
Match recent active jobs to a user's Auto Apply preferences and store the top
candidates in apply_queue.

score (0-100) blends whatever signals the user has:
- title:     target_roles vs job title (phrase or token overlap)
- role fit:  RelevanceScorer against the user's role profiles (User.job_roles)
- skills:    resume / profile skills found in the job description
Hard filters: excluded companies, ATS allowlist, locations/remote, salary floor.
"""
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from sqlalchemy import and_, or_, true
from sqlalchemy.orm import Session, joinedload

from services.apply.ats import detect_ats
from services.apply.constants import MATCH_LOOKBACK_DAYS, MATCH_MIN_SCORE_TO_STORE, QUEUE_SIZE

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9+#.]+")
_STOP = {"and", "or", "the", "of", "for", "a", "an", "in", "to", "with", "i", "ii", "iii", "-", "&"}
_SENIORITY = {"senior", "sr", "sr.", "staff", "principal", "lead", "junior", "jr", "jr.", "mid", "level"}


def _tokens(text: str) -> List[str]:
    return [t for t in _WORD_RE.findall((text or "").lower()) if t not in _STOP]


def _skill_vocabulary() -> Set[str]:
    from services.role_profiles_data import ROLE_PROFILES

    vocab: Set[str] = set()
    for profile in ROLE_PROFILES:
        for terms in (profile.get("positive_keywords") or {}).values():
            for term in terms:
                if 2 < len(term) <= 30:
                    vocab.add(term.lower())
    return vocab


_VOCAB: Optional[Set[str]] = None


def vocabulary() -> Set[str]:
    global _VOCAB
    if _VOCAB is None:
        try:
            _VOCAB = _skill_vocabulary()
        except Exception:
            _VOCAB = set()
    return _VOCAB


def extract_skills(text: str, extra: Optional[List[str]] = None) -> Set[str]:
    low = f" {(text or '').lower()} "
    found = {term for term in vocabulary() if re.search(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])", low)}
    for item in extra or []:
        item = (item or "").strip().lower()
        if item:
            found.add(item)
    return found


def title_score(title: str, target_roles: List[str]) -> Tuple[float, Optional[str]]:
    title_low = (title or "").lower()
    best, best_role = 0.0, None
    title_tokens = set(_tokens(title))
    for role in target_roles or []:
        role_low = role.strip().lower()
        if not role_low:
            continue
        if role_low in title_low:
            return 100.0, role
        role_tokens = [t for t in _tokens(role_low) if t not in _SENIORITY]
        if not role_tokens:
            continue
        overlap = sum(1 for t in role_tokens if t in title_tokens) / len(role_tokens)
        if overlap * 85 > best:
            best, best_role = overlap * 85, role
    return best, best_role


def location_ok(job_location: str, locations: List[str], remote_ok: bool) -> Tuple[bool, Optional[str]]:
    loc = (job_location or "").lower()
    is_remote = "remote" in loc
    if remote_ok and is_remote:
        return True, "Remote"
    if not locations:
        return True, None
    for wanted in locations:
        w = wanted.strip().lower()
        if w and w in loc:
            return True, f"Location: {wanted.strip()}"
    return False, None


class MatchContext:
    def __init__(self, user, prefs, resume_text: str = ""):
        from services.relevance_service import RelevanceScorer

        self.prefs = prefs
        roles = prefs.target_roles or user.job_titles or []
        self.target_roles = [r for r in roles if r and r.strip()]
        self.locations = [l for l in (prefs.locations or []) if l and l.strip()]
        self.remote_ok = bool(prefs.remote_ok)
        self.salary_floor = prefs.salary_floor
        self.excluded = [c.strip().lower() for c in (prefs.excluded_companies or []) if c and c.strip()]
        self.allowlist = set(prefs.ats_allowlist or [])
        extra = [s.strip() for s in (user.skills or "").split(",")] if user.skills else []
        self.skills = extract_skills(resume_text, extra)
        self.role_profiles = self._role_profiles(user)
        self.scorer = RelevanceScorer()

    @staticmethod
    def _role_profiles(user) -> List[Tuple[str, Dict[str, Any]]]:
        from services.role_profiles_data import get_profile_by_slug

        profiles = []
        for slug in (user.job_roles or [])[:5]:
            profile = get_profile_by_slug(slug)
            if profile:
                profiles.append((profile.get("name") or slug, profile))
        if not profiles and getattr(user, "role_profile", None) is not None:
            rp = user.role_profile
            profiles.append((rp.name, {
                "title_patterns": rp.title_patterns or {}, "positive_keywords": rp.positive_keywords or {},
                "negative_keywords": rp.negative_keywords or [], "seniority_config": rp.seniority_config or {},
                "relevance_threshold": rp.relevance_threshold or 30.0,
            }))
        return profiles


def score_job(job, ctx: MatchContext) -> Optional[Tuple[int, List[str], Optional[str]]]:
    """(score, reasons, ats) or None when a hard filter excludes the job."""
    company = (job.company.name if job.company else "") or ""
    if company and any(ex in company.lower() for ex in ctx.excluded):
        return None
    ref = detect_ats(job)
    if ctx.allowlist and ref.ats not in ctx.allowlist:
        return None
    ok, loc_reason = location_ok(job.location or "", ctx.locations, ctx.remote_ok)
    if not ok:
        return None
    if ctx.salary_floor and job.salary_max and job.salary_max < ctx.salary_floor:
        return None

    reasons: List[str] = []
    parts: List[Tuple[float, float]] = []  # (weight, score)

    if ctx.target_roles:
        t_score, role = title_score(job.title, ctx.target_roles)
        parts.append((0.5, t_score))
        if t_score >= 60 and role:
            reasons.append(f"Title matches “{role}”")

    if ctx.role_profiles:
        best, best_name = 0.0, None
        for name, profile in ctx.role_profiles:
            try:
                result = ctx.scorer.score(job.title or "", job.job_description or "", profile)
            except Exception:
                continue
            if result.relevance_score > best:
                best, best_name = result.relevance_score, name
        parts.append((0.3, best))
        if best >= 50 and best_name:
            reasons.append(f"Strong fit for {best_name}")

    if ctx.skills:
        job_text = f"{job.title or ''} {job.job_description or ''} {' '.join(job.ai_tech_stack or []) if isinstance(job.ai_tech_stack, list) else ''}"
        job_skills = extract_skills(job_text)
        overlap = sorted(ctx.skills & job_skills)
        denom = max(3, min(len(job_skills), 10)) if job_skills else 10
        s_score = min(100.0, 100.0 * len(overlap) / denom)
        parts.append((0.2, s_score))
        if overlap:
            reasons.append("Skills: " + ", ".join(overlap[:5]))

    if not parts:
        return None
    total_weight = sum(w for w, _ in parts)
    score = int(round(sum(w * s for w, s in parts) / total_weight))

    if loc_reason:
        reasons.append(loc_reason)
    if job.salary_max and ctx.salary_floor and job.salary_max >= ctx.salary_floor:
        reasons.append("Meets salary floor")
    if job.posted_date:
        days = max(0, (datetime.utcnow() - job.posted_date.replace(tzinfo=None)).days)
        reasons.append("Posted today" if days == 0 else f"Posted {days}d ago")
    return max(0, min(100, score)), reasons, ref.ats


MAX_LISTED_DAYS = 45  # listed_since older than this is too stale to apply to automatically


def is_stale_for_apply(job, now: Optional[datetime] = None) -> bool:
    """Evergreen/ghost posting, or listed for more than MAX_LISTED_DAYS."""
    if getattr(job, "is_evergreen", False):
        return True
    listed = getattr(job, "effective_posted_at", None)
    return bool(listed and ((now or datetime.utcnow()) - listed.replace(tzinfo=None)).days > MAX_LISTED_DAYS)


def user_country(user) -> str:
    """The user's country (ISO-2) for job visibility; US when unknown."""
    from services.job_location import normalize_country
    return (getattr(user, "country_code", None) or normalize_country(getattr(user, "country", None))
            or normalize_country(getattr(user, "address_country", None)) or "US")


def candidate_jobs(db: Session, limit: int = 5000, country: Optional[str] = None):
    from models import Job
    from services.job_location import country_filter

    now = datetime.utcnow()
    since = now - timedelta(days=MATCH_LOOKBACK_DAYS)
    listed_cutoff = now - timedelta(days=MAX_LISTED_DAYS)
    return (db.query(Job)
            .options(joinedload(Job.company))
            .filter(Job.is_active == True)  # noqa: E712
            .filter(Job.user_id.is_(None))  # shared scraped jobs, not users' manual entries
            .filter(or_(Job.posted_date >= since,
                        and_(Job.posted_date.is_(None), Job.created_at >= since)))
            # Never auto-apply to evergreen/ghost postings or ones listed > 45 days
            .filter(or_(Job.is_evergreen.is_(None), Job.is_evergreen == False))  # noqa: E712
            .filter(or_(Job.effective_posted_at >= listed_cutoff, Job.effective_posted_at.is_(None)))
            # Contract roles are not in jobs; skip any unrouted stragglers too.
            .filter(or_(Job.employment_type.is_(None),
                        Job.employment_type.notin_(("contract", "contract_to_hire", "freelance"))))
            .filter(country_filter(Job.country_codes, country) if country else true())
            .order_by(Job.posted_date.desc().nullslast(), Job.id.desc())
            .limit(limit)
            .all())


def build_queue(db: Session, user, prefs, resume_text: str = "") -> int:
    """Recompute the user's queue. Returns the number of stored items."""
    from models import Application, ApplyQueueItem

    ctx = MatchContext(user, prefs, resume_text)
    applied = {row[0] for row in db.query(Application.job_id).filter(Application.user_id == user.id).all()}
    scored = []
    for job in candidate_jobs(db, country=user_country(user)):
        if job.id in applied:
            continue
        result = score_job(job, ctx)
        if not result:
            continue
        score, reasons, ats = result
        if score >= MATCH_MIN_SCORE_TO_STORE:
            scored.append((score, job.id, reasons, ats))
    scored.sort(key=lambda x: (-x[0], -x[1]))
    top = scored[:QUEUE_SIZE]

    db.query(ApplyQueueItem).filter(ApplyQueueItem.user_id == user.id).delete(synchronize_session=False)
    now = datetime.utcnow()
    for score, job_id, reasons, ats in top:
        db.add(ApplyQueueItem(user_id=user.id, job_id=job_id, match_score=score, reasons=reasons,
                              ats=ats, created_at=now))
    prefs.queue_generated_at = now
    db.commit()
    return len(top)
