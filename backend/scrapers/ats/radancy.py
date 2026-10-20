"""
Radancy TalentBrew career sites as job_boards rows (ats "radancy").

Board: the site root with any locale path, "jobs.intuit.com" or
"jobs.walgreens.com/en"; results come from <board>/search-jobs/results.
Reuses RadancyMixin.
"""
from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import site_url
from scrapers.enterprise.radancy_scrapers import RadancyMixin


def _site(board: str):
    return site_url(board, min_segments=0, max_segments=2)


register(BoardType(
    name="radancy",
    mixin=RadancyMixin,
    valid=lambda board: _site(board) is not None,
    start_url=lambda board: f"{_site(board)}/search-jobs/results",
    careers_url=lambda board: f"{_site(board)}/search-jobs",
    attrs=lambda board: {"SITE_URL": _site(board)},
))
