"""
jobs.dedup_key: one posting listed more than once shares a key, so lists show it once.

- With a description (300+ characters of text): the title and the whole
  description (a long shared company intro must not merge two roles). Catches one posting on two boards (Salesforce's and
  Slack's Workday sites, Crusoe and Crusoe Energy) and one posting per city.
- Without: the title, the company and the location, so a board that lists the
  same opening twice with no text shows it once.

Lists keep the lowest id of each key among the rows that pass their own filters
(routes.jobs._distinct), so a city filter still finds that city's copy.
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
