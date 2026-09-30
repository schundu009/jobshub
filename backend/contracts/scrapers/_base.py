"""
Shared plumbing for the staffing-agency scrapers (contracts pipeline).

Every agency scraper subclasses StaffingScraper, which adds to HTTPScraper:

- polite pacing: at most one request per second per host (MIN_INTERVAL), on
  top of the per-run rate limiter the Celery task already applies;
- a time budget (TIME_BUDGET_SECONDS) and a cap on postings (MAX_JOBS, the
  most recent ones are kept) so a run fits inside the HTTP task's time limit;
- ``make_job`` to build a ScrapedJob with the contract fields
  (employment_type_raw, pay_rate_min/max, pay_period, extra) filled in;
- helpers for US-location checks and pay-text parsing;
- IT-only: every listing page goes through ``take_it`` (services.it_roles on the
  title, with the board's own category / skills as tie-breakers) before it is
  kept, so MAX_JOBS counts IT postings and paging continues past non-IT ones.
  Agencies whose API has a category filter also request only IT categories.

All network I/O goes through ``_http`` so offline tests can replace it.

Only public, unauthenticated endpoints that the agency's own careers site calls
from the browser are used, with the default client UA from HTTPScraper.
"""

import asyncio
import re
import time
from dataclasses import fields as dc_fields
from datetime import datetime, timezone
from typing import Any, Iterable, Optional
from urllib.parse import urlparse

from scrapers.base import HTTPScraper, ScrapedJob, ScrapeResult
from services.it_roles import is_it_role

STAFFING_CATEGORY = "staffing"

US_STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California",
    "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
    "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon",
    "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia",
    "WA": "Washington", "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "PR": "Puerto Rico", "GU": "Guam", "VI": "Virgin Islands",
}
_US_STATE_NAMES = {v.lower() for v in US_STATES.values()}
_US_COUNTRY = {"us", "usa", "u.s.", "u.s.a.", "united states", "united states of america"}

_NUM = r"\$?\s*(\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)\s*([kK])?"
# "<num> [up to ~25 chars of unit words] -|–|to <num>", e.g. "$108,000.00 USD Annually - $150,000.00"
_PAY_RANGE_RE = re.compile(_NUM + r"(?:[^\d\n]{0,25}?(?:-|–|\bto\b)\s*" + _NUM + r")?")
_PERIODS = (
    ("hour", re.compile(r"\b(hr|hrs|hour|hourly|per\s*hour|/\s*h)\b", re.I)),
    ("year", re.compile(r"\b(yr|year|yearly|annual|annually|annum|salary)\b", re.I)),
    ("day", re.compile(r"\b(day|daily)\b", re.I)),
    ("week", re.compile(r"\b(week|weekly|wk)\b", re.I)),
    ("month", re.compile(r"\b(month|monthly|mo)\b", re.I)),
)
_SCRAPED_FIELDS = {f.name for f in dc_fields(ScrapedJob)}


def norm_period(value: Optional[str]) -> Optional[str]:
    """'Hourly' / 'per hour' / 'PERHOUR' / 'Annually' -> hour | day | week | month | year."""
    if not value:
        return None
    v = str(value).lower().replace("_", " ")
    v = re.sub(r"^per", "per ", v)
    for name, rx in _PERIODS:
        if rx.search(v):
            return name
    return None


def to_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        f = float(str(value).replace(",", "").replace("$", "").strip())
    except ValueError:
        return None
    return f if f > 0 else None


def parse_pay_text(text: Optional[str]) -> tuple[Optional[float], Optional[float], Optional[str]]:
    """
    '$80-$85/hr W2', '70.00 - 75.00 | Per Hour', '$108,000.00 USD Annually - $150,000.00 USD
    Annually', '$120k - $140k' -> (min, max, period). Needs a period word or a 'k' suffix;
    returns (None, None, None) when no pay is recognised.
    """
    if not text:
        return None, None, None
    text = str(text)
    period = norm_period(text)
    m = _PAY_RANGE_RE.search(text.replace("USD", " "))
    if not m:
        return None, None, None

    def val(num, k):
        if num is None:
            return None
        f = float(num.replace(",", ""))
        return f * 1000 if k else f

    lo = val(m.group(1), m.group(2))
    hi = val(m.group(3), m.group(4) or m.group(2) if m.group(3) else None)
    if period is None and (m.group(2) or m.group(4)):
        period = "year"
    if period is None or not lo:
        return None, None, None
    if hi and hi < lo:
        lo, hi = hi, lo
    return lo, hi, period


def is_us_state(value: Optional[str]) -> bool:
    if not value:
        return False
    v = str(value).strip()
    return v.upper() in US_STATES or v.lower() in _US_STATE_NAMES


def is_us_country(value: Optional[str]) -> bool:
    return bool(value) and str(value).strip().lower() in _US_COUNTRY


def join_location(*parts: Optional[str]) -> str:
    return ", ".join(p.strip() for p in parts if p and str(p).strip())


def parse_iso(value: Any) -> Optional[datetime]:
    """ISO-8601 (Z / +00:00 / +0000 / fractional) or epoch millis -> naive UTC datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) or (isinstance(value, str) and value.isdigit()):
        try:
            return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).replace(tzinfo=None)
        except (ValueError, OverflowError, OSError):
            return None
    s = str(value).strip().replace("Z", "+00:00")
    s = re.sub(r"([+-]\d{2})(\d{2})$", r"\1:\2", s)
    # fromisoformat only accepts 0, 3 or 6 fractional digits before 3.11
    s = re.sub(r"\.(\d{1,6})\d*", lambda m: "." + m.group(1).ljust(6, "0"), s)
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        for fmt in ("%m-%d-%Y", "%m/%d/%Y", "%B %d, %Y", "%Y-%m-%d"):
            try:
                return datetime.strptime(str(value).strip(), fmt)
            except ValueError:
                continue
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


_LD_JSON_RE = re.compile(r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>', re.S | re.I)


def jsonld_job_description(html: Optional[str]) -> Optional[str]:
    """The schema.org JobPosting description (HTML) embedded in a posting page, or None."""
    import html as _html
    import json
    for block in _LD_JSON_RE.findall(html or ""):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        items = data if isinstance(data, list) else (data.get("@graph") or [data]) if isinstance(data, dict) else []
        for item in items:
            if isinstance(item, dict) and item.get("@type") == "JobPosting" and item.get("description"):
                desc = _html.unescape(str(item["description"]))
                if "&lt;" in desc or "&#" in desc:
                    desc = _html.unescape(desc)
                return desc.strip() or None
    return None


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")


def simple_employment_type(raw: Optional[str]) -> Optional[str]:
    """Agency job-type label -> the legacy ScrapedJob.employment_type bucket."""
    if not raw:
        return None
    v = raw.lower()
    if any(w in v for w in ("contract", "temp", "consult", "fixed term", "freelance", "locum", "1099")):
        return "contract"
    if any(w in v for w in ("perm", "direct", "full")):
        return "full-time"
    if "part" in v:
        return "part-time"
    return None


class StaffingScraper(HTTPScraper):
    """Base for staffing-agency scrapers. Subclasses implement fetch_raw() + parse_job()."""

    AGENCY_NAME: str = ""
    MIN_INTERVAL = 1.0  # seconds between requests to the same host
    TIME_BUDGET_SECONDS = 60  # + one in-flight request stays well under 75s
    MAX_JOBS = 2000  # IT postings kept per run

    # IT-only filter (services.it_roles). IT_AMBIGUOUS_DEFAULT decides titles
    # it_roles cannot settle ("Consultant", "Specialist") - True for boards whose
    # listing is already restricted to a technology category.
    IT_ONLY = True
    IT_AMBIGUOUS_DEFAULT = False
    # Keys read by the default it_view(); override it_view() for nested shapes.
    IT_TITLE_KEYS: tuple = ("title", "jobTitle", "jobtitle", "Title", "jobName")
    IT_CATEGORY_KEYS: tuple = ()
    IT_SKILLS_KEYS: tuple = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._last_hit: dict[str, float] = {}
        self._deadline: Optional[float] = None
        self.it_listed = 0  # postings seen in listing responses
        self.it_dropped = 0  # of those, dropped as non-IT

    # ------------------------------------------------------------ IT filter --

    @staticmethod
    def _text(value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, dict):
            value = value.get("description") or value.get("name") or value.get("title") or value.get("value")
        if isinstance(value, (list, tuple)):
            value = " ".join(t for t in (StaffingScraper._text(v) for v in value) if t)
        value = str(value).strip() if value is not None else ""
        return value or None

    @staticmethod
    def _skills(value: Any) -> list:
        if not value:
            return []
        if isinstance(value, str):
            return [s.strip() for s in re.split(r"[,;|]", value) if s.strip()]
        out = []
        for v in value if isinstance(value, (list, tuple)) else [value]:
            t = StaffingScraper._text(v)
            if t:
                out.append(t)
        return out

    def it_view(self, raw: Any) -> dict:
        """title / category / department / skills of one listing entry, for it_roles."""
        if not isinstance(raw, dict):
            return {"title": None}
        title = next((raw.get(k) for k in self.IT_TITLE_KEYS if raw.get(k)), None)
        category = " ".join(t for t in (self._text(raw.get(k)) for k in self.IT_CATEGORY_KEYS) if t) or None
        skills: list = []
        for k in self.IT_SKILLS_KEYS:
            skills.extend(self._skills(raw.get(k)))
        return {"title": title, "category": category, "skills": skills or None}

    def is_it_posting(self, raw: Any) -> bool:
        view = self.it_view(raw)
        if not view.get("title"):
            return True  # parse_job drops untitled rows anyway
        return is_it_role(view.get("title"), category=view.get("category"), department=view.get("department"),
                          skills=view.get("skills"), ambiguous_default=self.IT_AMBIGUOUS_DEFAULT)

    def take_it(self, items: Iterable) -> list:
        """Filter one listing page to IT postings (counted in it_listed / it_dropped)."""
        items = list(items or [])
        self.it_listed += len(items)
        if not self.IT_ONLY:
            return items
        kept = [r for r in items if self.is_it_posting(r)]
        self.it_dropped += len(items) - len(kept)
        return kept

    # ------------------------------------------------------------ network --

    async def _pace(self, url: str) -> None:
        host = urlparse(url).netloc
        last = self._last_hit.get(host)
        if last is not None:
            wait = self.MIN_INTERVAL - (time.monotonic() - last)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_hit[host] = time.monotonic()

    async def _http(
        self,
        method: str,
        url: str,
        *,
        params: Optional[dict] = None,
        json_body: Any = None,
        headers: Optional[dict] = None,
        expect: str = "json",
    ) -> Any:
        """One paced request; returns parsed JSON (expect='json') or text."""
        await self._pace(url)
        session = await self.get_session()
        async with session.request(
            method, url, params=params, json=json_body, headers=headers or {}
        ) as resp:
            resp.raise_for_status()
            if expect == "text":
                return await resp.text()
            return await resp.json(content_type=None)

    # Route the stock HTTPScraper helpers (used by reused mixins such as
    # PhenomMixin) through the paced _http as well.
    async def fetch_json(self, url, method="GET", params=None, json_data=None, headers=None,
                         payload=None, json=None):
        body = json_data if json_data is not None else (payload if payload is not None else json)
        return await self._http(method, url, params=params, json_body=body, headers=headers)

    async def fetch_html(self, url, params=None):
        return await self._http("GET", url, params=params, expect="text")

    # -------------------------------------------------------------- budget --

    def start_clock(self) -> None:
        self._deadline = time.monotonic() + self.TIME_BUDGET_SECONDS

    def out_of_time(self) -> bool:
        return self._deadline is not None and time.monotonic() > self._deadline

    # ------------------------------------------------------------- results --

    async def fetch_raw(self) -> list:
        """Return the raw postings (dicts); implemented by each agency."""
        raise NotImplementedError

    async def scrape(self) -> ScrapeResult:
        self.start_clock()
        self.it_listed = self.it_dropped = 0
        raw = await self.fetch_raw()
        jobs = self.finalize(self.parse_all(raw))
        if self.it_listed:
            self.logger.info(f"{self.config.company_slug}: {self.it_listed} listed, "
                             f"{self.it_dropped} non-IT dropped, {len(jobs)} kept")
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs))

    def finalize(self, jobs: Iterable[ScrapedJob]) -> list[ScrapedJob]:
        """Dedupe by external id, keep the MAX_JOBS most recently posted."""
        seen, out = set(), []
        for job in jobs:
            if job and job.external_job_id not in seen:
                seen.add(job.external_job_id)
                out.append(job)
        out.sort(key=lambda j: j.posted_date or datetime.min, reverse=True)
        return out[: self.MAX_JOBS]

    def make_job(
        self,
        *,
        title: str,
        location: str,
        job_url: str,
        external_job_id: Any,
        description: Optional[str] = None,
        posted_date: Optional[datetime] = None,
        employment_type_raw: Optional[str] = None,
        pay_min: Any = None,
        pay_max: Any = None,
        pay_period: Optional[str] = None,
        end_client: Optional[str] = None,
        department: Optional[str] = None,
        remote_type: Optional[str] = None,
        skills: Optional[list] = None,
        extra: Optional[dict] = None,
    ) -> Optional[ScrapedJob]:
        title = (title or "").strip()
        ext = str(external_job_id or "").strip()
        if not title or not ext or not job_url:
            return None

        lo, hi = to_float(pay_min), to_float(pay_max)
        period = norm_period(pay_period) if pay_period else None
        if lo is None and hi is not None:
            lo = hi
        if hi is not None and lo is not None and hi < lo:
            lo, hi = hi, lo
        if lo is None or period is None:
            lo = hi = period = None

        employment_type_raw = (employment_type_raw or "").strip() or None
        info = {"agency_name": self.AGENCY_NAME or self.config.company_name}
        client = (end_client or "").strip()
        if client and client.lower() not in ("confidential", "n/a", "na", "none", "client"):
            info["end_client"] = client
        if skills:
            info["skills"] = [s for s in skills if isinstance(s, str) and s.strip()][:40]
        if extra:
            info.update({k: v for k, v in extra.items() if v not in (None, "", [], {})})

        values = dict(
            title=title,
            location=(location or "").strip() or "United States",
            job_url=job_url,
            external_job_id=ext,
            job_description=description or None,
            department=department,
            posted_date=posted_date,
            employment_type=simple_employment_type(employment_type_raw),
            remote_type=remote_type,
            employment_type_raw=employment_type_raw,
            pay_rate_min=lo,
            pay_rate_max=hi,
            pay_period=period,
            extra=info,
        )
        if period == "year" and lo:
            values["salary_min"] = int(lo)
            values["salary_max"] = int(hi or lo)
        # Tolerate an older ScrapedJob without the contract fields.
        known = {k: v for k, v in values.items() if k in _SCRAPED_FIELDS}
        job = ScrapedJob(**known)
        for k, v in values.items():
            if k not in _SCRAPED_FIELDS:
                setattr(job, k, v)
        return job
