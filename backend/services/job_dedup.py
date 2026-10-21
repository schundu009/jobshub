"""
jobs.dedup_key: one posting listed more than once shares a key, so lists show it once.

- With a description (300+ characters of text): the title and the whole
  description (a long shared company intro must not merge two roles). Catches one posting on two boards (Salesforce's and
  Slack's Workday sites, Crusoe and Crusoe Energy) and one posting per city.
- Without: the title, the company and the location, so a board that lists the
  same opening twice with no text shows it once.

jobs.pay_key (pay_key below) catches what the description cannot: one employer's
several reqs for the same role, place and pay, each with its own team paragraph.

Lists keep a row only when it has the lowest id of its dedup_key AND of its
pay_key among the rows that pass their own filters (routes.jobs._distinct), so a
city filter still finds that city's copy.
"""
from __future__ import annotations

import hashlib
import re
from typing import Optional

MIN_DESC_CHARS = 300

_TAG = re.compile(r"<[^>]+>")
_NON_WORD = re.compile(r"[^a-z0-9]+")


def _norm(value: Optional[str]) -> str:
    return _NON_WORD.sub(" ", _TAG.sub(" ", (value or "").lower())).strip()


def dedup_key(title: Optional[str], company_id: Optional[int], location: Optional[str],
              description: Optional[str]) -> Optional[str]:
    """40-hex key, or None when there is no title."""
    t = _norm(title)
    if not t:
        return None
    d = _norm(description)
    if len(d) >= MIN_DESC_CHARS:
        basis = f"d|{t}|{d}"
    else:
        basis = f"l|{t}|{company_id or ''}|{_norm(location)}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()


_TRAILING_CODE = re.compile(r"\s*[(\[]\s*([A-Za-z]{2,4})\s*[)\]]\s*$")
# Office codes employers append to a req's title ("Forward Deployed Engineer (MTV)").
_OFFICE_CODES = frozenset((
    "NYC", "NY", "SF", "SFO", "SFBA", "MTV", "PAO", "SJC", "SEA", "LA", "LAX", "ATX", "AUS", "BOS", "CHI", "DC",
    "DEN", "ATL", "DAL", "PHX", "RDU", "SV", "BLR", "HYD", "PNQ", "LON", "LDN", "TOR", "YYZ", "DUB", "BER", "SYD",
))
# Parenthesised role words are part of the role, never an office.
_ROLE_CODES = frozenset(("AI", "ML", "QA", "UI", "UX", "BI", "IT", "HR", "AR", "VR", "SRE", "SDE", "SDET", "API", "GPU", "IOS"))


def _in_order(code: str, text: str) -> bool:
    it = iter(text)
    return all(ch in it for ch in code)


def _without_office_code(title: Optional[str], location: Optional[str]) -> Optional[str]:
    """The title without a trailing office code: "(MTV)" on a Mountain View req, "(NYC)"."""
    m = _TRAILING_CODE.search(title or "")
    if not m or not m.group(1).isupper() or m.group(1) in _ROLE_CODES:
        return title
    code, place = m.group(1).lower(), _NON_WORD.sub("", (location or "").lower())
    if m.group(1) in _OFFICE_CODES or (place and place[0] == code[0] and _in_order(code, place)):
        return title[:m.start()]
    return title


def pay_key(title: Optional[str], company_id: Optional[int], location: Optional[str],
            salary_min: Optional[int], salary_max: Optional[int]) -> Optional[str]:
    """jobs.pay_key: one company's same title, place and pay range, or None without a pay range.

    An employer that opens several reqs for one role (Intuit's five "Forward
    Deployed Engineer, Mountain View, $171K-$232K") writes each its own
    description, differing in a team paragraph, so dedup_key keeps them apart.
    To a job seeker they are one listing. Without a pay range the title alone is
    too broad ("Software Engineer" at a big company is many roles), so no key."""
    t = _norm(_without_office_code(title, location))
    if not t or not company_id or not (salary_min or salary_max):
        return None
    basis = f"p|{t}|{company_id}|{_norm(location)}|{salary_min or ''}|{salary_max or ''}"
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()
