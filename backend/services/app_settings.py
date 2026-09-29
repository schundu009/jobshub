"""
Typed access to AppSetting rows shared by the API and the Celery tasks.

Keys written by PUT /api/celery/schedules:
- scraper_interval_hours (int, 1-24): minimum gap between orchestrated scrapes
- auto_apply_enabled (bool): process_pending_applications runs only when true
- description_fetch_enabled (bool): fetch_missing_descriptions runs only when true

scraper_last_orchestrated_at (ISO datetime) is written by scrape_all_companies.
"""
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from models import AppSetting

SCRAPER_INTERVAL_KEY = "scraper_interval_hours"
AUTO_APPLY_ENABLED_KEY = "auto_apply_enabled"
DESCRIPTION_FETCH_ENABLED_KEY = "description_fetch_enabled"
SCRAPER_LAST_RUN_KEY = "scraper_last_orchestrated_at"


def get_setting(db: Session, key: str, default: Optional[str] = None) -> Optional[str]:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    return row.value if row and row.value is not None else default


def set_setting(db: Session, key: str, value: str, description: Optional[str] = None) -> None:
    """Upsert (caller commits)."""
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value, description=description))


def get_bool(db: Session, key: str, default: bool = True) -> bool:
    value = get_setting(db, key)
    if value is None:
        return default
    return value.strip().lower() in ("true", "1", "yes", "on")


def get_int(db: Session, key: str, default: int) -> int:
    value = get_setting(db, key)
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def get_datetime(db: Session, key: str) -> Optional[datetime]:
    value = get_setting(db, key)
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def schedule_settings(db: Session) -> dict:
    """The three admin-editable schedule settings with their defaults applied."""
    from config import settings

    return {
        "scraper_interval_hours": get_int(db, SCRAPER_INTERVAL_KEY, settings.scraper_schedule_hours),
        "auto_apply_enabled": get_bool(db, AUTO_APPLY_ENABLED_KEY, True),
        "description_fetch_enabled": get_bool(db, DESCRIPTION_FETCH_ENABLED_KEY, True),
    }
