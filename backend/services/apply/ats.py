"""
Identify a job's ATS and the identifiers needed to read its public form.

Order: the job URL (boards.greenhouse.io / job-boards.greenhouse.io / ?gh_jid=,
jobs.lever.co, jobs.ashbyhq.com), then the scraper that produced the job
(Job.source == scraper company_slug) whose API_URL names the board.
"""
import logging
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)


@dataclass
class AtsRef:
    ats: Optional[str]            # greenhouse | lever | ashby | workday | ... | None
    board: Optional[str] = None   # GH board token / Lever site / Ashby org
    posting_id: Optional[str] = None
    apply_url: Optional[str] = None

    @property
    def supported(self) -> bool:
        from services.apply.constants import SUPPORTED_ATS
        return self.ats in SUPPORTED_ATS and bool(self.board) and bool(self.posting_id)


_GH_BOARD_RE = re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/([^/?#]+)/jobs/(\d+)", re.I)
_GH_API_RE = re.compile(r"boards-api\.greenhouse\.io/v1/boards/([^/?#]+)", re.I)
_LEVER_RE = re.compile(r"jobs\.(?:eu\.)?lever\.co/([^/?#]+)/([0-9a-f-]{36})", re.I)
_LEVER_API_RE = re.compile(r"api\.(?:eu\.)?lever\.co/v0/postings/([^/?#]+)", re.I)
_ASHBY_RE = re.compile(r"jobs\.ashbyhq\.com/([^/?#]+)/([0-9a-f-]{36})", re.I)
_ASHBY_API_RE = re.compile(r"api\.ashbyhq\.com/posting-api/job-board/([^/?#]+)", re.I)

_OTHER_ATS = (
    ("myworkdayjobs", "workday"), ("workday", "workday"), ("icims", "icims"),
    ("taleo", "taleo"), ("brassring", "brassring"), ("jobvite", "jobvite"),
    ("smartrecruiters", "smartrecruiters"), ("eightfold", "eightfold"),
)

_registry_cache: Dict[str, Tuple[Optional[str], Optional[str]]] = {}


def greenhouse_apply_url(board: str, posting_id: str) -> str:
    return f"https://job-boards.greenhouse.io/{board}/jobs/{posting_id}"


def lever_apply_url(site: str, posting_id: str) -> str:
    return f"https://jobs.lever.co/{site}/{posting_id}/apply"


def ashby_apply_url(org: str, posting_id: str) -> str:
    return f"https://jobs.ashbyhq.com/{org}/{posting_id}/application"


def _registry_board(source: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """(ats, board) from the scraper registered under Job.source, if any."""
    if not source:
        return None, None
    if source in _registry_cache:
        return _registry_cache[source]
    result: Tuple[Optional[str], Optional[str]] = (None, None)
    try:
        from scrapers.registry import ScraperRegistry

        cls = ScraperRegistry.get(source)
        api_url = getattr(cls, "API_URL", None) if cls else None
        if api_url:
            for regex, ats in ((_GH_API_RE, "greenhouse"), (_LEVER_API_RE, "lever"), (_ASHBY_API_RE, "ashby")):
                m = regex.search(api_url)
                if m:
                    result = (ats, m.group(1))
                    break
    except Exception as e:  # registry import problems must not break the API
        logger.debug("scraper registry lookup failed for %s: %s", source, e)
    _registry_cache[source] = result
    return result


def detect_ats(job) -> AtsRef:
    url = (getattr(job, "job_url", None) or "").strip()
    external_id = (getattr(job, "external_job_id", None) or "").strip() or None

    m = _GH_BOARD_RE.search(url)
    if m:
        return AtsRef("greenhouse", m.group(1), m.group(2), url or greenhouse_apply_url(m.group(1), m.group(2)))

    m = _LEVER_RE.search(url)
    if m:
        return AtsRef("lever", m.group(1), m.group(2), lever_apply_url(m.group(1), m.group(2)))

    m = _ASHBY_RE.search(url)
    if m:
        return AtsRef("ashby", m.group(1), m.group(2), ashby_apply_url(m.group(1), m.group(2)))

    query = parse_qs(urlparse(url).query) if url else {}
    gh_jid = (query.get("gh_jid") or [None])[0]
    if "greenhouse.io/embed/job_app" in url.lower():
        board = (query.get("for") or [None])[0]
        token = (query.get("token") or [None])[0]
        if board and token:
            return AtsRef("greenhouse", board, token, url)

    reg_ats, reg_board = _registry_board(getattr(job, "source", None))
    if gh_jid or reg_ats == "greenhouse":
        posting_id = gh_jid or (external_id if external_id and external_id.isdigit() else None)
        board = reg_board if reg_ats == "greenhouse" else None
        return AtsRef("greenhouse", board, posting_id, url or (board and posting_id and greenhouse_apply_url(board, posting_id)))
    if reg_ats == "lever":
        return AtsRef("lever", reg_board, external_id, lever_apply_url(reg_board, external_id) if external_id else url)
    if reg_ats == "ashby":
        return AtsRef("ashby", reg_board, external_id, ashby_apply_url(reg_board, external_id) if external_id else url)

    lower = url.lower()
    for needle, name in _OTHER_ATS:
        if needle in lower:
            return AtsRef(name, None, None, url or None)
    return AtsRef(None, None, None, url or None)
