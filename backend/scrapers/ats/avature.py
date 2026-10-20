"""
Avature career portals as job_boards rows (ats "avature").

Board: the portal root (locale and portal path), "jobs.bmc.com/Careers" or
"careers.radpartners.com/careersmarketplace"; its search is
<board>/SearchJobs/. Reuses AvatureMixin (server-rendered result cards).

Some portal templates leave the location off the result card; their
JobDetail links still start with it ("/JobDetail/Nashville-Tennessee-United-
States-Patient-Service-Representative-Belle-Meade/20666"), so the words before
the title's own slug become the location.
"""
import re
from typing import Optional

from scrapers.ats import BoardType, register
from scrapers.ats._sitetext import site_url
from scrapers.base import ScrapedJob
from scrapers.enterprise.avature_scrapers import AvatureMixin

_WORDS = re.compile(r"[A-Za-z0-9]+")
_US_STATES = {
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware",
    "District of Columbia", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas",
    "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan", "Minnesota", "Mississippi",
    "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey", "New Mexico", "New York",
    "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island",
    "South Carolina", "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington",
    "West Virginia", "Wisconsin", "Wyoming",
}


def _portal(board: str):
    return site_url(board, min_segments=1, max_segments=3)


def location_from_slug(url: str, title: str) -> str:
    """The location words a JobDetail slug puts before the title ('' when it has none)."""
    m = re.search(r"/JobDetail/([^/?#]+)/\d+", url or "")
    title_words = [w.lower() for w in _WORDS.findall(title or "")]
    if not m or not title_words:
        return ""
    slug = [w for w in m.group(1).split("-") if w]
    lowered = [w.lower() for w in slug]
    for i in range(len(slug)):
        if lowered[i:i + len(title_words)] == title_words:
            words = slug[:i]
            break
    else:
        return ""
    if not words:
        return ""
    text = " ".join(words)
    # "Nashville Tennessee United States" -> "Nashville, Tennessee, United States"
    if text.endswith("United States"):
        head = text[: -len("United States")].strip()
        state = next((s for s in sorted(_US_STATES, key=len, reverse=True) if head.endswith(s)), None)
        city = head[: -len(state)].strip() if state else head
        return ", ".join(p for p in (city, state, "United States") if p)
    return text


class AvatureBoardMixin(AvatureMixin):
    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        job = super().parse_job(raw)
        if job and not job.location:
            job.location = location_from_slug(job.job_url, job.title)
        return job


register(BoardType(
    name="avature",
    mixin=AvatureBoardMixin,
    valid=lambda board: _portal(board) is not None,
    start_url=lambda board: f"{_portal(board)}/SearchJobs/",
    careers_url=lambda board: f"{_portal(board)}/SearchJobs/",
    attrs=lambda board: {"PORTAL_URL": _portal(board), "CONCURRENCY": 4},
))
