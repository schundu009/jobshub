"""
Scrapers for job_boards rows: a company added as data, not as a Python file.

A JobBoard row names an ATS and a board; build_scraper_class() turns it into
a registry scraper class from the same mixins the coded scrapers use, so its
runs are dispatched, saved and recorded exactly like theirs. The registry
(ScraperRegistry.get / get_metadata) falls back to these rows when no coded
scraper has the slug.
"""

import logging
import re
from typing import Optional

from scrapers.base import HTTPScraper, ScraperConfig, ScraperType
from scrapers.custom.remaining_scrapers import (
    AshbyMixin,
    GreenhouseMixin,
    LeverMixin,
    SmartRecruitersMixin,
    WorkdayMixin,
)
from scrapers.custom.jobdiva import JobDivaMixin, jobdiva_parts, jobdiva_portal_url
from scrapers.enterprise.icims_scrapers import ICIMSMixin
from scrapers.enterprise.successfactors_scrapers import SuccessFactorsMixin

logger = logging.getLogger(__name__)

BOARD_CATEGORY = "boards"

_MIXINS = {
    "greenhouse": GreenhouseMixin,
    "lever": LeverMixin,
    "ashby": AshbyMixin,
    "smartrecruiters": SmartRecruitersMixin,
    "workday": WorkdayMixin,
    "jobdiva": JobDivaMixin,
    "icims": ICIMSMixin,
    "successfactors": SuccessFactorsMixin,
}
SUPPORTED_ATS = tuple(_MIXINS)

_TOKEN = re.compile(r"[A-Za-z0-9_.\-]{1,120}")
_WORKDAY_HOST = re.compile(r"[a-z0-9\-]+\.wd\d+\.myworkdayjobs\.com")
_ICIMS_HOST = re.compile(r"[a-z0-9\-]+\.icims\.com")
# A SuccessFactors Career Site Builder site, usually on the company's own domain.
_SITE_HOST = re.compile(r"(?=.{4,253}$)(?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}")


def workday_parts(board: str) -> Optional[tuple[str, str, str]]:
    """"host/tenant/site" -> (host, tenant, site), or None when malformed."""
    parts = (board or "").split("/")
    if len(parts) != 3:
        return None
    host, tenant, site = parts
    if not _WORKDAY_HOST.fullmatch(host) or not _TOKEN.fullmatch(tenant) or not _TOKEN.fullmatch(site):
        return None
    return host, tenant, site


def api_url(ats: str, board: str) -> Optional[str]:
    """The ATS's public job-list API for a board, or None when ats/board is not usable."""
    if ats == "workday":
        parts = workday_parts(board)
        return f"https://{parts[0]}/wday/cxs/{parts[1]}/{parts[2]}/jobs" if parts else None
    if ats == "icims":
        return f"https://{board}/jobs/search" if _ICIMS_HOST.fullmatch(board or "") else None
    if ats == "successfactors":
        return f"https://{board}/search/" if _SITE_HOST.fullmatch(board or "") else None
    if ats == "jobdiva":
        # One API for every firm; the key keeps each board's URL distinct.
        parts = jobdiva_parts(board)
        return f"https://ws.jobdiva.com/candPortal/rest/job/searchjobsportal?a={parts[1]}" if parts else None
    if not _TOKEN.fullmatch(board or ""):
        return None
    if ats == "greenhouse":
        return f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs"
    if ats == "lever":
        return f"https://api.lever.co/v0/postings/{board}?mode=json"
    if ats == "ashby":
        return f"https://api.ashbyhq.com/posting-api/job-board/{board}"
    if ats == "smartrecruiters":
        return f"https://api.smartrecruiters.com/v1/companies/{board}/postings"
    return None


def board_careers_url(ats: str, board: str) -> Optional[str]:
    """The public board page, for rows saved without a careers URL."""
    if ats == "workday":
        parts = workday_parts(board)
        return f"https://{parts[0]}/{parts[2]}" if parts else None
    if ats == "jobdiva":
        return jobdiva_portal_url(board)
    if ats in ("icims", "successfactors"):
        return api_url(ats, board)
    return {
        "greenhouse": f"https://job-boards.greenhouse.io/{board}",
        "lever": f"https://jobs.lever.co/{board}",
        "ashby": f"https://jobs.ashbyhq.com/{board}",
        "smartrecruiters": f"https://jobs.smartrecruiters.com/{board}",
    }.get(ats)


class BoardScraper(HTTPScraper):
    """Base of every job_boards scraper; the ATS mixin supplies scrape() and parse_job()."""
    BOARD_ATS: str = ""
    BOARD: str = ""


_class_cache: dict[tuple, type] = {}


def build_scraper_class(board: dict) -> Optional[type]:
    """
    A scraper class for one job_boards row (as dict: slug, company_name, ats,
    board, careers_url). None when the ATS is unsupported or the board malformed.
    """
    ats = board.get("ats")
    url = api_url(ats, board.get("board"))
    if ats not in _MIXINS or not url:
        return None
    key = (board["slug"], board["company_name"], ats, board["board"], board.get("careers_url"))
    if key in _class_cache:
        return _class_cache[key]
    attrs = {
        "config": ScraperConfig(
            company_slug=board["slug"],
            company_name=board["company_name"],
            careers_url=board.get("careers_url") or board_careers_url(ats, board["board"]) or url,
            scraper_type=ScraperType.HTTP,
            rate_limit=30,
            max_pages=20,
        ),
        "API_URL": url,
        "BOARD_ATS": ats,
        "BOARD": board["board"],
        "__module__": __name__,
    }
    if ats == "smartrecruiters":
        attrs["COMPANY_ID"] = board["board"]
    if ats == "icims":
        attrs["ICIMS_HOST"] = board["board"]
    if ats == "successfactors":
        attrs["SF_HOST"] = board["board"]
    name = re.sub(r"[^A-Za-z0-9]", "", board["slug"].title()) or "Board"
    cls = type(f"{name}BoardScraper", (_MIXINS[ats], BoardScraper), attrs)
    _class_cache[key] = cls
    return cls


def board_metadata(board: dict) -> dict:
    """Registry metadata (the keys coded scrapers have) for a job_boards row."""
    cls = build_scraper_class(board)
    return {
        "category": BOARD_CATEGORY,
        "company_name": board["company_name"],
        "scraper_type": ScraperType.HTTP.value,
        "careers_url": cls.config.careers_url if cls else (board.get("careers_url") or ""),
        "rate_limit": 30,
        "ats": board.get("ats"),
        "board": board.get("board"),
    }


def _as_dict(row) -> dict:
    return {
        "slug": row.slug, "company_name": row.company_name, "ats": row.ats,
        "board": row.board, "careers_url": row.careers_url, "enabled": bool(row.enabled),
        "max_age_days": getattr(row, "max_age_days", None),
    }


def load_board(slug: str) -> Optional[dict]:
    """The enabled job_boards row for a slug, or None (also when the DB can't be read)."""
    try:
        from database import SessionLocal
        from models import JobBoard

        with SessionLocal() as db:
            row = db.query(JobBoard).filter(JobBoard.slug == slug, JobBoard.enabled == True).first()  # noqa: E712
            return _as_dict(row) if row else None
    except Exception as e:
        logger.debug(f"job_boards lookup for {slug} skipped: {e}")
        return None


def load_boards() -> list[dict]:
    """Every enabled job_boards row ([] when the DB can't be read)."""
    try:
        from database import SessionLocal
        from models import JobBoard

        with SessionLocal() as db:
            rows = db.query(JobBoard).filter(JobBoard.enabled == True).order_by(JobBoard.slug).all()  # noqa: E712
            return [_as_dict(r) for r in rows]
    except Exception as e:
        logger.debug(f"job_boards listing skipped: {e}")
        return []


def ats_of(scraper_cls) -> str:
    """The ATS a scraper class reads (greenhouse, ..., workday), else "other"."""
    if getattr(scraper_cls, "BOARD_ATS", None):
        return scraper_cls.BOARD_ATS
    for name, mixin in _MIXINS.items():
        if isinstance(scraper_cls, type) and issubclass(scraper_cls, mixin):
            return name
    from services.ats_detect import match_url
    hit = match_url(getattr(scraper_cls, "API_URL", None) or "")
    return hit[0] if hit else "other"
