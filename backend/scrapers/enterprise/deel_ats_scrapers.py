"""
Deel ATS job boards (jobs.deel.com/{board}), pure HTTP.

Boards are Next.js App Router pages with no client-side JSON API: the full
posting list is server-rendered into the React Server Components ("flight")
stream, i.e. the self.__next_f.push([1, "..."]) script chunks of the page.
Decoding and concatenating those strings yields JSON posting objects shaped
    {"id", "jobId", "title", "createdAt", "updatedAt",
     "job": {"workArrangementEnum", "jobLocations": [{"location": {"name"}}],
             "jobEmploymentTypes": [...], "jobDepartments": [...],
             "currentCompensation": {...}},
     "jobPostingPublications": [{"currentState": {"stateSlug"}}]}
which are cut out with JSONDecoder.raw_decode. One request returns every
posting (the board has no paging). Postings are at
jobs.deel.com/{board}/job-details/{id}/overview.

Deel's own board (jobs.deel.com/deel) redirects to www.deel.com/careers/, a
Next.js marketing page whose flight stream holds a different record shape
({"id": n, "attributes": {"ashby_id", "title", "all_locations",
"external_link": "https://jobs.deel.com/deel/job-details/<id>/application", ...}});
those are parsed too so the same mixin covers it.

Verified 2026-09-29.
"""

import json
import re
from datetime import datetime
from typing import Dict, List, Optional

from scrapers.base import ScrapedJob, ScrapeResult, UnexpectedResponseError

_FLIGHT_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_BOARD_POSTING_RE = re.compile(r'\{"id":"[0-9a-f-]{36}","jobId":"')
_CAREERS_RECORD_RE = re.compile(r'\{"id":\d+,"attributes":\{"ashby_id":"')
_WORK_ARRANGEMENTS = {"REMOTE": "remote", "HYBRID": "hybrid", "ON_SITE": "on-site"}


def decode_flight(html: str) -> str:
    """Concatenate the string chunks of a Next.js RSC flight stream."""
    return "".join(json.loads(chunk) for chunk in _FLIGHT_CHUNK_RE.findall(html))


def _objects(flight: str, pattern: re.Pattern) -> List[dict]:
    decoder = json.JSONDecoder()
    out = []
    for m in pattern.finditer(flight):
        try:
            obj, _ = decoder.raw_decode(flight, m.start())
        except ValueError:
            continue
        out.append(obj)
    return out


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _names(entries: list, key: str) -> List[str]:
    out = []
    for entry in entries or []:
        name = ((entry or {}).get(key) or {}).get("name")
        if name and name not in out:
            out.append(name)
    return out


class DeelATSMixin:
    """Subclasses set BOARD (the slug in jobs.deel.com/{board})."""

    BOARD: str = ""
    MAX_JOBS = 1500

    def board_url(self) -> str:
        return f"https://jobs.deel.com/{self.BOARD}"

    def posting_url(self, posting_id: str) -> str:
        return f"https://jobs.deel.com/{self.BOARD}/job-details/{posting_id}/overview"

    async def scrape(self) -> ScrapeResult:
        html = await self.fetch_html(self.resolve_api_url(self.board_url()))
        flight = decode_flight(html)
        if not flight:
            raise UnexpectedResponseError("no Next.js flight data in Deel job board page")
        raw_jobs = self.extract_postings(flight)
        jobs = self.parse_all(raw_jobs[: self.MAX_JOBS])
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), pages_scraped=1)

    def extract_postings(self, flight: str) -> List[dict]:
        """Unique posting dicts, tagged with "_shape" ("board" or "careers")."""
        found: Dict[str, dict] = {}
        for obj in _objects(flight, _BOARD_POSTING_RE):
            if obj.get("title") and isinstance(obj.get("job"), dict) and self._is_published(obj):
                found.setdefault(obj["id"], {**obj, "_shape": "board"})
        if not found:
            for obj in _objects(flight, _CAREERS_RECORD_RE):
                attrs = obj.get("attributes") or {}
                if attrs.get("title") and attrs.get("is_listed", True):
                    found.setdefault(attrs["ashby_id"], {**attrs, "_shape": "careers"})
        return list(found.values())

    @staticmethod
    def _is_published(obj: dict) -> bool:
        pubs = obj.get("jobPostingPublications")
        if not pubs:
            return True
        return any(
            ((p or {}).get("currentState") or {}).get("stateSlug", "").startswith("published")
            for p in pubs
        )

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        try:
            if raw.get("_shape") == "careers":
                return self._parse_careers_record(raw)
            return self._parse_board_posting(raw)
        except Exception as e:
            self.logger.error(f"Error parsing Deel ATS job: {e}")
            return None

    def _parse_board_posting(self, raw: dict) -> Optional[ScrapedJob]:
        title = (raw.get("title") or "").strip()
        posting_id = raw.get("id")
        if not title or not posting_id:
            return None
        job = raw.get("job") or {}
        departments = _names(job.get("jobDepartments"), "department") or _names(job.get("jobTeams"), "team")
        employment = _names(job.get("jobEmploymentTypes"), "employmentType")
        salary_min = salary_max = None
        comp = job.get("currentCompensation") or {}
        if raw.get("isCompensationVisible") and comp:
            salary_min = int(comp["minAmount"]) if comp.get("minAmount") is not None else None
            salary_max = int(comp["maxAmount"]) if comp.get("maxAmount") is not None else None
        return ScrapedJob(
            title=title,
            location="; ".join(_names(job.get("jobLocations"), "location")),
            job_url=self.posting_url(posting_id),
            external_job_id=str(posting_id),
            department=departments[0] if departments else None,
            employment_type=employment[0] if employment else None,
            remote_type=_WORK_ARRANGEMENTS.get(job.get("workArrangementEnum")),
            posted_date=_parse_iso(raw.get("createdAt")),
            salary_min=salary_min,
            salary_max=salary_max,
        )

    def _parse_careers_record(self, raw: dict) -> Optional[ScrapedJob]:
        title = (raw.get("title") or "").strip()
        posting_id = raw.get("ashby_id")
        if not title or not posting_id:
            return None
        locations = [l for l in (raw.get("all_locations") or []) if l] or (
            [raw["location_name"]] if raw.get("location_name") else []
        )
        link = raw.get("external_link") or ""
        job_url = re.sub(r"/application/?$", "/overview", link) if "/job-details/" in link else self.posting_url(posting_id)
        return ScrapedJob(
            title=title,
            location="; ".join(dict.fromkeys(locations)),
            job_url=job_url,
            external_job_id=str(posting_id),
            department=raw.get("team_name") or raw.get("tier_2_category") or None,
            employment_type=raw.get("employment_type") or None,
            posted_date=_parse_iso(raw.get("ashby_published_date")),
        )
