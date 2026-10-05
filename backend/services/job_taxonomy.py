"""
The labels the jobs filters group by: a job's role category and seniority, and its company's domain.

- role_category: services.it_roles.it_category (the same classifier that keeps non-IT jobs out),
  "other" when it is not an IT role. Set on save (models.py) and backfilled (migrations/job_taxonomy.py).
- seniority: from the title alone. Its own rules, not firm_matching.title_level: that one scores a
  match, so "Product Manager" reads as lead there; here a manager is someone who manages people.
- domain: a company's primary business, from data/company_domains.json (company name -> slug).
  NULL = not classified yet; add the company to the file.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

ROLE_CATEGORIES = {
    "software": "Software Engineering",
    "devops_sre_cloud": "DevOps, SRE & Cloud",
    "data": "Data Engineering & Analytics",
    "ml_ai": "AI & Machine Learning",
    "security": "Security",
    "network_systems_dba": "Networks, Systems & DBA",
    "qa": "QA & Testing",
    "embedded_hw": "Embedded & Hardware",
    "it_support": "IT Support",
    "product_program": "Product & Program",
    "design_ux": "Design & UX",
    "tech_writing": "Technical Writing",
    "other": "Other",
}

SENIORITIES = {
    "intern": "Intern",
    "entry": "Entry level",
    "mid": "Mid level",
    "senior": "Senior",
    "lead_staff": "Lead / Staff / Principal",
    "manager": "Manager",
    "director_exec": "Director & Executive",
}

DOMAINS = {
    "ai": "AI",
    "cloud_infrastructure": "Cloud & Infrastructure",
    "enterprise_software": "Enterprise Software",
    "cybersecurity": "Cybersecurity",
    "consumer_internet": "Consumer Internet",
    "streaming_media": "Streaming & Media",
    "gaming": "Gaming",
    "ecommerce_retail": "E-commerce & Retail",
    "semiconductors_hardware": "Semiconductors & Hardware",
    "telecom": "Telecom",
    "banking": "Banking",
    "financial_services": "Financial Services",
    "insurance": "Insurance",
    "crypto_web3": "Crypto & Web3",
    "consulting_it_services": "Consulting & IT Services",
    "staffing_recruiting": "Staffing & Recruiting",
    "healthcare": "Healthcare",
    "biotech_pharma": "Biotech & Pharma",
    "manufacturing_industrial": "Manufacturing & Industrial",
    "automotive_mobility": "Automotive & Mobility",
    "aerospace_defense": "Aerospace & Defense",
    "energy_utilities": "Energy & Utilities",
    "logistics_transportation": "Logistics & Transportation",
    "travel_hospitality": "Travel & Hospitality",
    "real_estate_proptech": "Real Estate",
    "education": "Education",
    "government_public_sector": "Government & Public Sector",
    "other": "Other",
}


# ------------------------------------------------------------------ role category

def role_category(title: Optional[str], department: Optional[str] = None) -> str:
    from services.it_roles import it_category
    try:
        return it_category(title, department=department) or "other"
    except Exception:  # never block a save over a label
        return "other"


# ------------------------------------------------------------------ seniority

def _rx(body: str) -> re.Pattern:
    return re.compile(r"(?<![a-z0-9])(?:" + body + r")(?![a-z0-9])", re.I)


# First match wins, most specific first.
_SENIORITY_RULES = (
    ("intern", _rx(r"intern|internship|co-?op|apprentice(?:ship)?|working student|werkstudent|trainee|stagiaire|praktikant\w*")),
    ("director_exec", _rx(r"director|vp|svp|evp|avp|vice president|head of|chief|cto|cio|ciso")),
    # a people manager; product / program / project / account managers are individual contributors
    ("manager", _rx(r"(?:engineering|software|development|dev|technical|tech|team|it|delivery|data|security|"
                    r"infrastructure|platform|qa|quality|test|sre|devops|cloud|network|operations)\s+manager|"
                    r"manager,?\s+(?:of\s+)?(?:engineering|software|development|data|security|infrastructure|"
                    r"platform|sre|devops|it|technology)|manager\s+-\s+engineering")),
    ("lead_staff", _rx(r"staff|principal|distinguished|fellow|lead")),
    ("senior", _rx(r"senior|sr|snr|iii|iv|level 3|level iii|expert")),
    ("entry", _rx(r"junior|jr|entry|entry-level|graduate|grad|new grad|early career|university|campus|fresher|i|level 1|associate")),
    ("mid", _rx(r"mid|mid-level|intermediate|ii|level 2")),
)


# Banks put a corporate title after the role ("Java Developer - Vice President"): a VP there is a
# senior individual contributor, not an executive.
_BANK_TITLE = re.compile(r"\s*[,\-–|/]\s*(?:assistant vice president|vice president|avp|vp|associate)\s*$", re.I)
_IC_MANAGER = re.compile(r"(?:product|program|project|account|marketing|sales)\s+manager", re.I)


def _level(t: str) -> str:
    for level, rx in _SENIORITY_RULES:
        m = rx.search(t)
        if not m:
            continue
        if level == "manager" and _IC_MANAGER.search(t[max(0, m.start() - 12):m.end()]):
            continue
        return level
    return "mid"  # a title with no level word is a mid-level posting


def seniority(title: Optional[str]) -> str:
    t = re.sub(r"[._]", " ", str(title or "")).strip()
    m = _BANK_TITLE.search(t)
    if m:
        level = _level(t[:m.start()])
        if "vice president" in m.group(0).lower() or re.search(r"\bv\s*p\b", m.group(0), re.I):
            return "senior" if level in ("mid", "entry") else level
        return level
    return _level(t)


# ------------------------------------------------------------------ company domain

_LEGAL = re.compile(r"[,\s]+(inc|llc|llp|corp|corporation|co|ltd|limited|plc|lp|gmbh|ag|sa|bv|nv|se|pte)\.?$", re.I)
_DATA = Path(__file__).resolve().parent.parent / "data" / "company_domains.json"


def company_key(name: Optional[str]) -> str:
    n = str(name or "").strip()
    for _ in range(3):
        n = _LEGAL.sub("", n).strip(" ,.")
    return re.sub(r"[^a-z0-9]+", "", n.lower())


@lru_cache(maxsize=1)
def _domain_map() -> dict:
    try:
        raw = json.loads(_DATA.read_text())
    except (OSError, ValueError):
        return {}
    return {company_key(k): v for k, v in raw.items() if v in DOMAINS}


def company_domain(name: Optional[str]) -> Optional[str]:
    """Domain slug for a company name, None when it is not in data/company_domains.json."""
    key = company_key(name)
    return _domain_map().get(key) if key else None
