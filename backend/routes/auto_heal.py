"""
Auto-heal trigger endpoint — called by Railway cron daily.

Secured with X-Internal-Key header matching INTERNAL_API_KEY env var.
Triggers the Celery auto_heal_scrapers task and returns the result.
"""

import os
import secrets
import logging
from fastapi import APIRouter, Header, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/internal", tags=["auto-heal"])

_INTERNAL_KEY = os.environ.get("INTERNAL_API_KEY", "")


def _verify_key(x_internal_key: str = Header(default="")):
    if not _INTERNAL_KEY or not secrets.compare_digest(x_internal_key, _INTERNAL_KEY):
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/auto-heal")
def trigger_auto_heal(x_internal_key: str = Header(default="")):
    """
    Trigger the auto_heal_scrapers Celery task synchronously and return its result.
    Called by Railway cron: POST /api/internal/auto-heal with X-Internal-Key header.
    """
    _verify_key(x_internal_key)

    try:
        from tasks.maintenance_tasks import auto_heal_scrapers
        result = auto_heal_scrapers.apply().get(timeout=300)
        logger.info(f"[AutoHeal] Cron trigger complete: {result}")
        return {"status": "ok", "result": result}
    except Exception as e:
        logger.exception("[AutoHeal] Cron trigger failed")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auto-heal/status")
def heal_status(x_internal_key: str = Header(default="")):
    """Return current scraper failure counts."""
    _verify_key(x_internal_key)

    from database import SessionLocal
    from models import ScraperConfigDB

    with SessionLocal() as db:
        broken = db.query(ScraperConfigDB).filter(
            ScraperConfigDB.consecutive_failures >= 3
        ).order_by(ScraperConfigDB.consecutive_failures.desc()).all()

        disabled = db.query(ScraperConfigDB).filter(
            ScraperConfigDB.is_enabled == False
        ).all()

    return {
        "broken": [
            {
                "slug": s.company_slug,
                "failures": s.consecutive_failures,
                "overrides": s.config_overrides,
                "last_failure": s.last_failure_at.isoformat() if s.last_failure_at else None,
            }
            for s in broken
        ],
        "disabled": [s.company_slug for s in disabled],
    }
