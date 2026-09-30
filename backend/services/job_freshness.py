"""
Freshness model for the full-time jobs table.

Boards re-date postings and keep "evergreen" ones up forever, so our own
sightings are ground truth:
- effective posted date = the EARLIER of the ATS posted_date and first_seen_at
- evergreen/ghost postings: talent_pool (resume collectors), reposted
  (reappears under new ids / re-dated), long_listed (listed > 60 days)
Pure functions; the save path and the backfill call apply_freshness().
"""
from __future__ import annotations

import html as _html
import re
from datetime import datetime, timezone
from typing import Any, Optional

I = re.IGNORECASE
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def to_text(value: Optional[str], limit: int = 20000) -> str:
    if not value:
        return ""
    s = _html.unescape(str(value))
    s = _TAG_RE.sub(" ", s)
    s = _html.unescape(s).replace("\u00a0", " ")
    return _WS_RE.sub(" ", s).strip()[:limit]


LONG_LISTED_DAYS = 60
REPOST_WINDOW_DAYS = 90
REPOSTS_FOR_EVERGREEN = 2

_TALENT_POOL_TITLE = re.compile(
    r"\btalent\s+(community|pool|network|pipeline)\b|\bgeneral\s+(application|interest|applications)\b|"
    r"\bfuture\s+(opportunit\w*|openings?|roles?|positions?|needs)\b|\bexpressions?\s+of\s+interest\b|"
    r"\bevergreen\b|\balways\s+hiring\b|\(\s*pipeline\s*\)|\bpipeline\s*[-–:|]\s|\s[-–:|]\s*pipeline\b|"
    r"\bdon'?t\s+see\s+(a|the|your)\s+(role|fit|job|position)\b|\bsubmit\s+your\s+(resume|cv)\b|\bopen\s+application\b", I)
_TALENT_POOL_DESC = re.compile(
    r"\b(this|the)\s+(posting|position|role|requisition|req|opportunity|listing|job|application|opening)\s+"
    r"(is|will be used|serves|is being used)\s+(\w+\s+){0,6}?(talent\s+(pool|community|network|pipeline)|pipeline|"
    r"future\s+(opportunities|openings|roles|needs|positions)|evergreen|general\s+application)\b|"
    r"\b(we\s+are|we're)\s+always\s+hiring\b|\bexpressions?\s+of\s+interest\b|"
    r"\bnot\s+(tied\s+to|for)\s+an?\s+(specific|current|active|open|immediate)\s+(opening|role|position|vacancy|requisition)\b|"
    r"\bevergreen\s+(role|position|requisition|req|posting|opening|job)\b|"
    r"\bjoin\s+our\s+talent\s+(network|community|pool)\b(?=[^.]{0,80}\b(this|posting|role|position)\b)", I)


def is_talent_pool(title: Optional[str], description: Optional[str] = None) -> bool:
    """Postings that collect resumes rather than fill a specific opening."""
    if title and _TALENT_POOL_TITLE.search(title):
        return True
    text = to_text(description, limit=20000)
    return bool(text and _TALENT_POOL_DESC.search(text))


def _naive(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if not isinstance(dt, datetime):
        try:
            dt = datetime(dt.year, dt.month, dt.day)
        except Exception:
            return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def effective_posted_at(posted_date: Optional[datetime], first_seen_at: Optional[datetime]) -> Optional[datetime]:
    """The earlier of the ATS posted date and our first sighting (re-dated postings can't look new)."""
    dates = [d for d in (_naive(posted_date), _naive(first_seen_at)) if d is not None]
    return min(dates) if dates else None


def listed_days(effective: Optional[datetime], now: Optional[datetime] = None) -> Optional[int]:
    effective = _naive(effective)
    if effective is None:
        return None
    return max(0, ((now or datetime.utcnow()) - effective).days)


def evergreen_status(
    title: Optional[str],
    description: Optional[str],
    days_listed: Optional[int],
    reposted_count: Optional[int],
) -> tuple[bool, Optional[str]]:
    """(is_evergreen, reason): talent_pool > reposted > long_listed."""
    if is_talent_pool(title, description):
        return True, "talent_pool"
    if (reposted_count or 0) >= REPOSTS_FOR_EVERGREEN:
        return True, "reposted"
    if days_listed is not None and days_listed > LONG_LISTED_DAYS:
        return True, "long_listed"
    return False, None


_TITLE_NOISE = re.compile(r"\s*[\(\[]?\b(req(uisition)?|job|id)\s*[#:.-]?\s*[\w-]*\d[\w-]*[\)\]]?\s*$|\s*[\(\[]\s*\d+\s*[\)\]]\s*$", I)


def normalize_title(title: Optional[str]) -> str:
    """Title key for repost detection: lowercase, collapsed spaces, trailing req ids dropped."""
    t = _WS_RE.sub(" ", (title or "").strip().lower())
    t = _TITLE_NOISE.sub("", t)
    return t.strip(" -–|,")


def apply_freshness(job: Any, now: Optional[datetime] = None) -> None:
    """Recompute is_evergreen / evergreen_reason on a Job-like object in place."""
    eff = effective_posted_at(getattr(job, "posted_date", None), getattr(job, "first_seen_at", None))
    ev, reason = evergreen_status(job.title, getattr(job, "job_description", None),
                                  listed_days(eff, now), getattr(job, "reposted_count", 0))
    job.is_evergreen = ev
    job.evergreen_reason = reason


def touch_seen(job: Any, now: Optional[datetime] = None, is_new: bool = False) -> None:
    """A scrape (re)listed this Job: move last_seen_at, keep the earliest listing date, recompute evergreen."""
    now = now or datetime.utcnow()
    if is_new or getattr(job, "first_seen_at", None) is None:
        job.first_seen_at = getattr(job, "first_seen_at", None) or now
    job.last_seen_at = now
    job.effective_posted_at = effective_posted_at(
        effective_posted_at(getattr(job, "effective_posted_at", None), getattr(job, "posted_date", None)),
        job.first_seen_at)
    if getattr(job, "reposted_count", None) is None:
        job.reposted_count = 0
    apply_freshness(job, now)
    from services.job_location import job_countries, to_country_codes
    job.country_codes = to_country_codes(job_countries(getattr(job, "location", None), job.title))
