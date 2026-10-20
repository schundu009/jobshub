"""
Phenom People career sites as job_boards rows (ats "phenom").

Board: the site root with its country and language path, as the search page
shows it: "careers.asurion.com/us/en" (search at /us/en/search-results).
The scrape reuses PhenomMixin: refNum, locale and pageId come from the
search-results page, then the /widgets refineSearch JSON is paged.
"""
from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import site_url
from scrapers.enterprise.phenom_scrapers import PhenomMixin


def _site(board: str):
    return site_url(board, min_segments=1, max_segments=3)


register(BoardType(
    name="phenom",
    mixin=PhenomMixin,
    valid=lambda board: _site(board) is not None,
    start_url=lambda board: f"{_site(board)}/search-results",
    careers_url=lambda board: f"{_site(board)}/search-results",
    attrs=lambda board: {"SITE_URL": _site(board), "MAX_JOBS": 1500},
))
