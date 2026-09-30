"""
Allegis Group staffing brands on Phenom career sites: TEKsystems, Aerotek, Actalent.

Endpoint: the Phenom search-results page (for refNum/locale/pageId) and then
``POST {host}/widgets`` with ddoKey=refineSearch - the same JSON call the career
site makes in the browser (see scrapers/enterprise/phenom_scrapers.py). Phenom's
search ignores sortBy, so the whole US board is read in pages of 500 (a few
requests) and the most recent MAX_JOBS postings are kept.

The listing has the job type ("Contractor", "Contract to Hire", "Permanent",
...) and a teaser that usually states the rate ("Compensation: $80-$85/hr W2").

IT only: the widgets call takes ``selected_fields: {"category": [...]}`` (the
site's own category facet), so only IT categories are requested (API_CATEGORIES),
and every page is then filtered with services.it_roles (StaffingScraper.take_it)
using the Phenom category as the tie-breaker.
Verified 2026-09-29.
"""

import re
from typing import Optional
from urllib.parse import urlparse

from scrapers.base import ScraperConfig, ScraperType, UnexpectedResponseError
from scrapers.enterprise.phenom_scrapers import PhenomMixin, _phenom_setting, parse_phenom_ddo
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, is_us_country, parse_iso, parse_pay_text, slugify

_PAY_SNIPPET_RE = re.compile(
    r"(?:compensation|pay(?:\s*rate)?|rate|salary)\s*[:\-]?\s*(\$[^.;|]{1,80}?"
    r"(?:/\s*h(?:ou)?r|per\s*hour|hourly|/\s*yr|per\s*year|annually|annual|/\s*year|\bhr\b|\bk\b))",
    re.I,
)


def pay_from_teaser(*texts: Optional[str]):
    for text in texts:
        if not text:
            continue
        m = _PAY_SNIPPET_RE.search(text)
        if m:
            lo, hi, period = parse_pay_text(m.group(1))
            if lo:
                return lo, hi, period
    return None, None, None


class AllegisPhenomScraper(StaffingScraper):
    """Read a whole Phenom board through /widgets, keep the most recent US postings."""

    SITE_URL = ""
    PAGE_SIZE = 500
    FETCH_LIMIT = 10000  # Elasticsearch result window
    # Optional allowlist of Phenom "category" values (None = keep all).
    CATEGORIES: Optional[set] = None
    # Categories requested from the API (the site's facet filter); None = all.
    API_CATEGORIES: Optional[list] = None
    IT_CATEGORY_KEYS = ("category", "subCategory")
    IT_SKILLS_KEYS = ("ml_skills",)

    def _payload(self, settings: dict, offset: int, size: int) -> dict:
        payload = PhenomMixin._widget_payload(self, settings, offset, size)
        if self.API_CATEGORIES:
            payload["selected_fields"] = {"category": list(self.API_CATEGORIES)}
        return payload

    def _host(self) -> str:
        u = urlparse(self.SITE_URL)
        return f"{u.scheme}://{u.netloc}"

    async def fetch_raw(self) -> list:
        html = await self._http("GET", f"{self.SITE_URL.rstrip('/')}/search-results", expect="text")
        settings = {k: _phenom_setting(html, k) for k in ("refNum", "locale", "country", "pageId")}
        if not all(settings.values()):
            # Fall back to the jobs embedded in the page itself.
            first, _ = PhenomMixin._unpack(parse_phenom_ddo(html).get("eagerLoadRefineSearch"))
            if self.API_CATEGORIES:
                first = [j for j in first if j.get("category") in self.API_CATEGORIES]
            return self.take_it(first)

        raw, offset, total = [], 0, None
        while offset < self.FETCH_LIMIT:
            size = self.PAGE_SIZE if total is None else min(self.PAGE_SIZE, total - offset)
            if size <= 0:
                break
            payload = self._payload(settings, offset, size)
            data = await self._http("POST", f"{self._host()}/widgets", json_body=payload)
            search = data.get("refineSearch") if isinstance(data, dict) else None
            if offset == 0:
                jobs, total = PhenomMixin._unpack(search)
            else:
                jobs = ((search or {}).get("data") or {}).get("jobs") or []
            if not jobs:
                break
            raw.extend(self.take_it(jobs))
            offset += len(jobs)
            if (total is not None and offset >= total) or self.out_of_time():
                break
        if not raw and total:
            raise UnexpectedResponseError(f"Phenom reported {total} jobs but returned none")
        return raw

    def parse_job(self, raw: dict):
        country = raw.get("country")
        if country and not is_us_country(country):
            return None
        if self.CATEGORIES is not None and raw.get("category") not in self.CATEGORIES:
            return None
        job_id = str(raw.get("jobId") or raw.get("reqId") or "").strip()
        title = (raw.get("title") or "").strip()
        if not job_id or not title:
            return None
        parser = raw.get("ml_job_parser") or {}
        if not isinstance(parser, dict):
            parser = {}
        teaser = raw.get("descriptionTeaser") or parser.get("descriptionTeaser")
        pay_texts = (parser.get("descriptionTeaser_first200"), parser.get("descriptionTeaser_keyword"),
                     parser.get("descriptionTeaser_ats"), teaser)
        lo, hi, period = pay_from_teaser(*pay_texts)
        description = teaser
        full = parser.get("descriptionTeaser_first200")
        if full and full not in (teaser or ""):
            description = f"{full}\n\n{teaser or ''}".strip()
        location = raw.get("location") or raw.get("cityStateCountry") or ""
        if not location and raw.get("multi_location"):
            location = raw["multi_location"][0]
        return self.make_job(
            title=title,
            location=location,
            job_url=f"{self.SITE_URL.rstrip('/')}/job/{job_id}/{slugify(title)}",
            external_job_id=job_id,
            description=description,
            posted_date=parse_iso(raw.get("postedDate") or raw.get("dateCreated")),
            employment_type_raw=raw.get("type"),
            pay_min=lo, pay_max=hi, pay_period=period,
            department=raw.get("category"),
            skills=raw.get("ml_skills"),
            extra={"subcategory": raw.get("subCategory")},
        )


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class TEKsystemsScraper(AllegisPhenomScraper):
    config = ScraperConfig(
        company_slug="teksystems",
        company_name="TEKsystems",
        careers_url="https://careers.teksystems.com/us/en/search-results",
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "TEKsystems"
    SITE_URL = "https://careers.teksystems.com/us/en"
    # Every TEKsystems category except "Customer Service" (call-center work);
    # "Other" and "Telecom Technician" are mixed and settled per title.
    API_CATEGORIES = [
        "Helpdesk/Desktop", "Developer", "Systems Administrator/Engineer", "Network Engineer",
        "Business/Systems Analyst", "Project Manager", "Architect", "Security Analyst/Engineer",
        "Database Administrator", "Tester", "Telecom Technician", "Other",
    ]


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class AerotekScraper(AllegisPhenomScraper):
    config = ScraperConfig(
        company_slug="aerotek",
        company_name="Aerotek",
        careers_url="https://jobs.aerotek.com/us/en/search-results",
        scraper_type=ScraperType.HTTP,
        # Works (7,455 US postings on 2026-09-29, ~85% "Contractor"), but every
        # category is industrial: Manufacturing & Production, Construction,
        # Facilities, Distribution, Aviation. Flip on to include light-industrial
        # contract work in the contracts pipeline.
        enabled=False,
        disabled_reason="no tech categories (industrial/light-industrial board only)",
    )
    AGENCY_NAME = "Aerotek"
    SITE_URL = "https://jobs.aerotek.com/us/en"


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class ActalentScraper(AllegisPhenomScraper):
    config = ScraperConfig(
        company_slug="actalent",
        company_name="Actalent",
        careers_url="https://careers.actalentservices.com/us/en/search-results",
        scraper_type=ScraperType.HTTP,
    )
    AGENCY_NAME = "Actalent"
    SITE_URL = "https://careers.actalentservices.com/us/en"
    # Software/IT, plus Manufacturing/Mechanical/Electrical for the embedded /
    # electronics roles in it (the per-title IT filter drops the rest). Power,
    # civil, construction, lab, clinical and medical categories are not requested.
    API_CATEGORIES = ["Systems & Software", "Manufacturing, Mechanical, & Electrical"]
    CATEGORIES = set(API_CATEGORIES)
