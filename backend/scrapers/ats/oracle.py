"""
Oracle Recruiting Cloud (HCM Candidate Experience) as job_boards rows (ats "oracle").

Board: "<hcm host>/<site number>", e.g. "ecge.fa.us2.oraclecloud.com/CX_1003"
(the host and the sites/<number> segment of the career site's address).
Reuses OracleHCMMixin (recruitingCEJobRequisitions REST, 200 per page).
"""
import re

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import host_and_path
from scrapers.enterprise.oracle import OracleHCMMixin

_SITE_NUMBER = re.compile(r"[A-Za-z0-9_]{1,40}")


def _parts(board: str):
    parsed = host_and_path(board, min_segments=1, max_segments=1)
    if not parsed or not _SITE_NUMBER.fullmatch(parsed[1][0]):
        return None
    return parsed[0], parsed[1][0]


def _api(board: str) -> str:
    return f"https://{_parts(board)[0]}/hcmRestApi/resources/latest/recruitingCEJobRequisitions"


def _careers(board: str) -> str:
    host, site = _parts(board)
    return f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/jobs"


register(BoardType(
    name="oracle",
    mixin=OracleHCMMixin,
    valid=lambda board: _parts(board) is not None,
    start_url=_api,
    careers_url=_careers,
    attrs=lambda board: {"HCM_HOST": _parts(board)[0], "SITE_NUMBER": _parts(board)[1], "MAX_JOBS": 1600},
))
