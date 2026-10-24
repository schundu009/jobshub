"""
IT staffing vendors scraped as company boards (job_boards rows, own-site
scrapers): their postings are mostly client reqs on C2C / W2 rates, so their
boards route with the staffing rule (contracts.classifier.contract_routing
staffing=True, description evidence counts) instead of the company-board rule
(ATS field or title only). A vendor's posting that says full-time stays in jobs.

Not here: permanent-placement recruiters (Michael Page, Harnham, Redfish), whose
"contractor" wording is usually the client's trade, and employers that post
hourly roles (Target).
"""
from __future__ import annotations

import re
from typing import Optional

CONTRACT_VENDORS = (
    "Akraya",
    "Aditi Consulting",
    "ApTask",
    "Beacon Hill",
    "Crystal Equation",
    "Diverse Lynx",
    "HYR Global Source",
    "ICONMA",
    "INSPYR Solutions",
    "Lorven Technologies",
    "Mitchell Martin",
    "My3Tech",
    "Primary Talent Partners",
    "Pyramid Consulting",
    "Rang Technologies",
    "Russell Tobin",
    "Techgene Solutions",
    "The Carrera Agency",
    "US Tech Solutions",
    "VDart",
    "Yochana",
)

_SUFFIX = re.compile(r"\b(inc|llc|ltd|corp|corporation|global workforce)\b\.?", re.I)


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _SUFFIX.sub("", name.lower()))


_KEYS = frozenset(_key(n) for n in CONTRACT_VENDORS)


def is_contract_vendor(company_name: Optional[str]) -> bool:
    """True for a company on CONTRACT_VENDORS ('Akraya, Inc.' and 'akraya' alike)."""
    return bool(company_name) and _key(company_name) in _KEYS
