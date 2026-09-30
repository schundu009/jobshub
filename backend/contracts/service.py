"""
Saving and expiring contract roles (contract_jobs).

- 30-day window (AppSetting contract_max_age_days, default 30) on the
  effective posted date = earlier of posted_date and our first sighting.
- Dedupe on (source, external_job_id); re-seen rows are refreshed.
- One bad row never poisons the batch (savepoint per row, session recovered
  after connection-level errors).
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts.classifier import CONTRACT_TYPES, classify, raw_fields_from_scraped
from contracts.models import ContractJob
from services.job_location import to_country_codes

logger = logging.getLogger(__name__)

CONTRACT_MAX_AGE_KEY = "contract_max_age_days"
DEFAULT_CONTRACT_MAX_AGE_DAYS = 30
_HOURS = {"hour": 1.0, "day": 8.0, "week": 40.0, "month": 2080.0 / 12, "year": 2080.0}

SKILL_VOCAB = (
    "python", "java", "javascript", "typescript", "react", "angular", "vue", "node.js", "go", "golang", "rust",
    "c#", ".net", "c++", "scala", "kotlin", "swift", "php", "ruby", "sql", "postgresql", "mysql", "oracle",
    "mongodb", "redis", "kafka", "spark", "hadoop", "airflow", "snowflake", "databricks", "dbt", "tableau",
    "power bi", "aws", "azure", "gcp", "kubernetes", "docker", "terraform", "ansible", "jenkins", "linux",
    "salesforce", "servicenow", "sap", "workday", "peoplesoft", "mainframe", "cobol", "selenium", "cypress",
    "machine learning", "pytorch", "tensorflow", "llm", "etl", "informatica", "splunk", "devops", "sre",
    "microservices", "spring", "spring boot", "django", "flask", "fastapi", "graphql", "rest", "ios", "android",
    "figma", "jira", "scrum", "agile", "cissp", "sailpoint", "okta", "cyberark", "network", "cisco", "vmware",
)
_SKILL_RX = [(s, re.compile(r"(?<![\w.#+])" + re.escape(s) + r"(?![\w#+])", re.I)) for s in SKILL_VOCAB]


def extract_skills(title: str, text: str, extra: Optional[Iterable[str]] = None, limit: int = 15) -> list[str]:
    hay = f"{title or ''} {text or ''}"[:20000]
    found = [s for s, rx in _SKILL_RX if rx.search(hay)]
    for s in extra or []:
        s = str(s).strip()
        if s and s.lower() not in {f.lower() for f in found}:
            found.append(s)
    return found[:limit]


def hourly_equivalent(value: Optional[float], period: Optional[str]) -> Optional[float]:
    if value is None or period not in _HOURS:
        return None
    return round(float(value) / _HOURS[period], 2)


def contract_max_age_days(db: Session) -> int:
    try:
        from models import AppSetting
        row = db.query(AppSetting.value).filter(AppSetting.key == CONTRACT_MAX_AGE_KEY).first()
        return max(1, int(row[0])) if row and row[0] else DEFAULT_CONTRACT_MAX_AGE_DAYS
    except Exception:
        return DEFAULT_CONTRACT_MAX_AGE_DAYS


def _naive(value) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, datetime):
        try:
            value = datetime(value.year, value.month, value.day)
        except Exception:
            return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return value if value.year >= 2000 else None


def effective_date(posted: Optional[datetime], first_seen: Optional[datetime]) -> Optional[datetime]:
    dates = [d for d in (_naive(posted), _naive(first_seen)) if d is not None]
    return min(dates) if dates else None


def _clip(value, n: Optional[int] = None) -> Optional[str]:
    if value is None:
        return None
    value = str(value).replace("\x00", "").strip()
    if n and len(value) > n:
        value = value[: n - 1].rstrip() + "…"
    return value or None


def _external_id(scraped) -> str:
    ext = _clip(getattr(scraped, "external_job_id", None)) or scraped.generate_id()
    return hashlib.md5(ext.encode()).hexdigest() if len(ext) > 255 else ext


def _is_connection_error(exc: BaseException) -> bool:
    from sqlalchemy.exc import DBAPIError, OperationalError, PendingRollbackError
    return isinstance(exc, (OperationalError, PendingRollbackError)) or (
        isinstance(exc, DBAPIError) and bool(getattr(exc, "connection_invalidated", False)))


def _recover(db: Session) -> None:
    """After a failed row: if the outer transaction is dead, start a fresh one."""
    try:
        tx = db.get_transaction()
        if tx is not None and not tx.is_active:
            db.rollback()
    except Exception:
        try:
            db.rollback()
        except Exception:
            pass


@dataclass
class ContractSaveResult:
    new: int = 0
    updated: int = 0
    skipped_old: int = 0
    skipped_invalid: int = 0
    skipped_not_contract: int = 0
    duplicates: int = 0
    errors: int = 0
    expired: int = 0
    first_error: Optional[str] = None

    @property
    def saved(self) -> int:
        return self.new + self.updated

    def as_dict(self) -> dict:
        return dict(self.__dict__)


def classify_scraped(scraped, default_type: Optional[str] = "contract") -> dict:
    """Contract fields for one ScrapedJob (employment_type falls back to default_type)."""
    raw = raw_fields_from_scraped(scraped)
    fields = classify(scraped.title, scraped.job_description, scraped.location, raw)
    if fields["employment_type"] is None and default_type:
        fields["employment_type"] = default_type
    return fields


def save_contract_jobs(
    db: Session,
    source: str,
    jobs: list,
    source_type: str = "staffing",
    company_id: Optional[int] = None,
    agency_name: Optional[str] = None,
    commit: bool = True,
    now: Optional[datetime] = None,
    classified: Optional[dict] = None,
) -> ContractSaveResult:
    """
    Upsert contract postings for one source.

    ``classified`` maps id(scraped_job) -> classify() output when the caller
    already classified (the full-time bridge), to avoid doing it twice.
    Staffing postings the classifier calls full-time/part-time/internship
    ("Direct Hire", "Permanent") are skipped (skipped_not_contract).
    """
    stats = ContractSaveResult()
    if not jobs:
        return stats
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=contract_max_age_days(db))
    classified = classified or {}

    prepared = []
    seen: set[str] = set()
    for scraped in jobs:
        try:
            title = _clip(scraped.title, 500)
            if not title:
                stats.skipped_invalid += 1
                continue
            ext = _external_id(scraped)
            if ext in seen:
                stats.duplicates += 1
                continue
            seen.add(ext)
            fields = classified.get(id(scraped)) or classify_scraped(
                scraped, default_type="contract" if source_type == "staffing" else None)
            if fields.get("employment_type") not in CONTRACT_TYPES:
                stats.skipped_not_contract += 1
                continue
            prepared.append((scraped, ext, title, fields))
        except Exception as e:
            stats.errors += 1
            stats.first_error = stats.first_error or f"{type(e).__name__}: {e}"[:200]

    existing: dict[str, ContractJob] = {}
    ids = [p[1] for p in prepared]
    for i in range(0, len(ids), 500):
        for row in db.query(ContractJob).filter(
            ContractJob.source == source, ContractJob.external_job_id.in_(ids[i:i + 500])
        ).all():
            existing[row.external_job_id] = row

    for scraped, ext, title, fields in prepared:
        posted = _naive(scraped.posted_date)
        row = existing.get(ext)
        eff = effective_date(posted, row.first_seen_at if row else now)
        if eff is not None and eff < cutoff:
            stats.skipped_old += 1
            if row is not None and row.is_active:
                row.is_active = False
                stats.expired += 1
            continue
        extra = getattr(scraped, "extra", None) or {}
        values = dict(
            title=title,
            location=_clip(scraped.location, 500),
            country_codes=to_country_codes(fields["countries"]),
            job_url=_clip(scraped.job_url),
            description=_clip(scraped.job_description),
            posted_date=posted,
            employment_type=fields["employment_type"],
            tax_terms=fields["tax_terms"],
            pay_rate_min=fields["pay_rate_min"],
            pay_rate_max=fields["pay_rate_max"],
            pay_period=fields["pay_period"],
            hourly_rate_min=hourly_equivalent(fields["pay_rate_min"], fields["pay_period"]),
            hourly_rate_max=hourly_equivalent(fields["pay_rate_max"] or fields["pay_rate_min"], fields["pay_period"]),
            contract_duration_months=fields["contract_duration_months"],
            visa_terms=fields["visa_terms"],
            skills=extract_skills(title, fields.get("_text") or scraped.job_description or "",
                                  extra.get("skills") if isinstance(extra, dict) else None) or None,
            agency_name=_clip(agency_name or (extra.get("agency_name") if isinstance(extra, dict) else None), 255),
            end_client=_clip(extra.get("end_client") if isinstance(extra, dict) else None, 255),
            last_seen_at=now,
            effective_posted_at=eff or now,
            is_active=True,
            source_type=source_type,
            company_id=company_id,
        )
        try:
            with db.begin_nested():
                if row is not None:
                    for k, v in values.items():
                        if k == "description" and not v:
                            continue
                        setattr(row, k, v)
                    db.flush()
                    stats.updated += 1
                else:
                    db.add(ContractJob(source=source, external_job_id=ext, first_seen_at=now, **values))
                    db.flush()
                    stats.new += 1
        except IntegrityError:
            stats.duplicates += 1
            _recover(db)
        except Exception as e:
            stats.errors += 1
            stats.first_error = stats.first_error or f"{type(e).__name__}: {str(e).splitlines()[0][:200]}"
            logger.warning(f"contract save failed for {source}/{ext}: {e}")
            _recover(db)

    if commit:
        try:
            db.commit()
        except Exception as e:
            db.rollback()
            stats.first_error = stats.first_error or f"commit: {type(e).__name__}: {e}"[:200]
            stats.errors += stats.new + stats.updated
            stats.new = stats.updated = 0
    return stats


def deactivate_unseen(db: Session, source: str, seen_external_ids: set[str], commit: bool = True) -> int:
    """A successful scrape that no longer lists a posting closes it."""
    if not seen_external_ids:
        return 0
    n = db.query(ContractJob).filter(
        ContractJob.source == source,
        ContractJob.is_active == True,  # noqa: E712
        ~ContractJob.external_job_id.in_(list(seen_external_ids)),
    ).update({"is_active": False}, synchronize_session=False)
    if commit:
        db.commit()
    return n


def expire_contract_jobs(db: Session, now: Optional[datetime] = None, commit: bool = True) -> int:
    """Deactivate active contract roles whose effective posted date is past the window."""
    now = now or datetime.utcnow()
    cutoff = now - timedelta(days=contract_max_age_days(db))
    n = db.query(ContractJob).filter(
        ContractJob.is_active == True,  # noqa: E712
        or_(ContractJob.effective_posted_at < cutoff,
            and_(ContractJob.effective_posted_at.is_(None), ContractJob.first_seen_at < cutoff)),
    ).update({"is_active": False}, synchronize_session=False)
    if commit:
        db.commit()
    if n:
        logger.info(f"Expired {n} contract jobs older than {cutoff:%Y-%m-%d}")
    return n
