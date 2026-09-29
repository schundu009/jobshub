"""
Company name normalization and lookup.

Jobs were being saved under several rows for one employer ('roblox' vs
'Roblox', 'Snap' vs 'Snap Inc.', 'Apply.Careers.Microsoft.Com' vs 'Microsoft'),
so the row the admin UI and scraper stats look at showed 0 jobs. Every
job-saving path resolves companies through here, by a normalized key:

    normalize_company_key("T-Mobile USA, Inc.") == normalize_company_key("T-Mobile") == "tmobile"

Only shared rows (user_id IS NULL) are matched; users' private companies are
never merged into or matched against.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from models import Company

logger = logging.getLogger(__name__)

# Trailing tokens that don't distinguish companies ("Snap Inc." == "Snap").
_SUFFIX_TOKENS = {
    "inc", "incorporated", "llc", "ltd", "limited", "corp", "corporation", "co",
    "company", "group", "technologies", "technology", "usa", "us", "plc", "gmbh",
    "holdings", "the",
}
_PREFIX_TOKENS = {"the"}

# Domain-looking names ("amazon.com", "apply.careers.microsoft.com") -> the
# registrable label.
_DOMAIN_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*\.(com|io|co|ai|net|org|dev|app|jobs|careers)$")
_DOMAIN_NOISE_LABELS = {"www", "jobs", "careers", "apply", "boards", "job-boards", "career", "en", "us"}

# Normalized key -> canonical normalized key, for names the rules above can't unify.
ALIASES = {
    "applycareersmicrosoftcom": "microsoft",
    "careersmicrosoft": "microsoft",
    "meta1": "meta",
    "metaplatforms": "meta",
    "blocksquare": "block",
    "squareblock": "block",
    "paloalto": "paloaltonetworks",
    "scale": "scaleai",
    "together": "togetherai",
    "jpmorganchase": "jpmorgan",
    "jpmorganchaseco": "jpmorgan",
    "jpmorganco": "jpmorgan",
    "tmobileusa": "tmobile",
    "snapinc": "snap",
    "delltechnologies": "dell",
    "expediagroup": "expedia",
    "unitytechnologies": "unity",
    "amazoncom": "amazon",
    "amazonwebservices": "amazon",
}


def _ascii(value: str) -> str:
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")


def normalize_company_key(name: Optional[str]) -> str:
    """Case/punctuation/suffix-insensitive key for a company name ('' for blank)."""
    if not name:
        return ""
    text = _ascii(name).strip().lower()

    # A bare domain: keep the label before the TLD, skipping jobs/careers/www.
    if " " not in text and _DOMAIN_RE.match(text):
        labels = [label for label in text.split(".")[:-1] if label not in _DOMAIN_NOISE_LABELS]
        if labels:
            text = labels[-1]

    text = text.replace("&", " ")
    tokens = [t for t in re.split(r"[^a-z0-9]+", text) if t]
    if not tokens:
        return ""

    stripped = list(tokens)
    while len(stripped) > 1 and stripped[-1] in _SUFFIX_TOKENS:
        stripped.pop()
    while len(stripped) > 1 and stripped[0] in _PREFIX_TOKENS:
        stripped.pop(0)

    key = "".join(stripped)
    full = "".join(tokens)
    return ALIASES.get(key) or ALIASES.get(full) or key


def registry_company_keys() -> dict[str, str]:
    """Normalized key -> registry slug for every registered scraper."""
    from scrapers.registry import ScraperRegistry

    keys: dict[str, str] = {}
    for slug in ScraperRegistry.list_slugs():
        metadata = ScraperRegistry.get_metadata(slug) or {}
        for candidate in (metadata.get("company_name"), slug):
            key = normalize_company_key(candidate)
            if key:
                keys.setdefault(key, slug)
    return keys


def registry_display_names() -> dict[str, str]:
    """Normalized key -> ScraperConfig.company_name for every registered scraper."""
    from scrapers.registry import ScraperRegistry

    names: dict[str, str] = {}
    for slug in ScraperRegistry.list_slugs():
        name = (ScraperRegistry.get_metadata(slug) or {}).get("company_name")
        key = normalize_company_key(name)
        if key and name:
            names.setdefault(key, name)
    return names


class CompanyResolver:
    """
    Finds or creates shared Company rows by normalized key.

    Loads (id, name) of all shared companies once, lazily, so one resolver per
    batch keeps lookups O(1). Not thread-safe; use one per session.
    """

    def __init__(self, db: Session):
        self.db = db
        self._by_key: Optional[dict[str, list[tuple[int, str]]]] = None
        self._display_names: Optional[dict[str, str]] = None

    def _index(self) -> dict[str, list[tuple[int, str]]]:
        if self._by_key is None:
            self._by_key = {}
            rows = self.db.query(Company.id, Company.name).filter(
                Company.user_id.is_(None)
            ).order_by(Company.id).all()
            for cid, cname in rows:
                key = normalize_company_key(cname)
                if key:
                    self._by_key.setdefault(key, []).append((cid, cname))
        return self._by_key

    def preferred_name(self, name: str) -> str:
        """The registry's company_name for this key if one exists, else ``name``."""
        if self._display_names is None:
            try:
                self._display_names = registry_display_names()
            except Exception:
                self._display_names = {}
        return self._display_names.get(normalize_company_key(name), name)

    def find(self, name: Optional[str], prefer_name: Optional[str] = None) -> Optional[Company]:
        key = normalize_company_key(name)
        if not key:
            return None
        matches = self._index().get(key)
        if not matches:
            return None
        chosen = matches[0][0]
        for want in (prefer_name, name):
            if not want:
                continue
            for cid, cname in matches:
                if cname == want:
                    chosen = cid
                    break
            else:
                continue
            break
        return self.db.get(Company, chosen)

    def get_or_create(
        self,
        name: str,
        website: Optional[str] = None,
        prefer_name: Optional[str] = None,
    ) -> Company:
        """
        Existing shared company with the same normalized key, else a new one.
        New rows use ``prefer_name`` (e.g. the scraper's ScraperConfig.company_name)
        or the registry's name for that key, falling back to ``name``.
        """
        name = (name or "").strip() or "Unknown"
        company = self.find(name, prefer_name=prefer_name)
        if company:
            if website and not company.website:
                company.website = website
            return company

        display = prefer_name or self.preferred_name(name)
        company = Company(name=display[:255], website=website)
        self.db.add(company)
        self.db.flush()
        key = normalize_company_key(display) or normalize_company_key(name)
        self._index().setdefault(key, []).append((company.id, company.name))
        logger.info(f"Created new company: {company.name} (ID: {company.id})")
        return company


def group_duplicates(rows: Iterable[tuple[int, str, Optional[int]]]) -> dict[tuple[Optional[int], str], list[tuple[int, str]]]:
    """(id, name, user_id) rows -> {(user_id, key): [(id, name), ...]} for keys with 2+ rows."""
    groups: dict[tuple[Optional[int], str], list[tuple[int, str]]] = {}
    for cid, cname, uid in rows:
        key = normalize_company_key(cname)
        if key:
            groups.setdefault((uid, key), []).append((cid, cname))
    return {k: v for k, v in groups.items() if len(v) > 1}
