"""
Rippling ATS boards as job_boards rows (ats "rippling").

Board: the board slug of ats.rippling.com/<board>/jobs (also the
data-job-board-id of an embedded rr-job-board), e.g. "hammerspace".
Reuses RipplingATSMixin.
"""
from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import is_token
from scrapers.enterprise.rippling_ats_scrapers import RipplingATSMixin

register(BoardType(
    name="rippling",
    mixin=RipplingATSMixin,
    valid=is_token,
    start_url=lambda board: f"https://ats.rippling.com/api/v2/board/{board}/jobs",
    careers_url=lambda board: f"https://ats.rippling.com/{board}/jobs",
))
