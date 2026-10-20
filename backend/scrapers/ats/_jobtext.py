"""
Text helpers shared by the board types in this package (not a board type:
load_all() skips modules whose name starts with "_").

- label_value(): "Location: Phoenix, AZ" style lines in a posting's text;
- jsonld_postings() / jsonld_location() / jsonld_pay(): schema.org JobPosting
  blocks embedded in a posting page;
- html_text(): description HTML -> one-line text for label searches;
- pay_from_text(): the contracts pay parser on a pay-labelled line;
- robots_allows(): services.robots for HTML career pages, off the event loop.
"""

import asyncio
import html as _html
import json
import re
from typing import Iterable, Optional

from contracts.scrapers._base import norm_period, parse_pay_text, to_float

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
_LD_JSON = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.S | re.I)
_COUNTRY_NAMES = {"US": "United States", "USA": "United States", "GB": "United Kingdom", "UK": "United Kingdom",
                  "CA": "Canada", "AU": "Australia", "IE": "Ireland", "DE": "Germany", "IN": "India"}


def html_text(value: Optional[str]) -> str:
    """HTML -> plain text on one line (entities decoded, tags dropped)."""
    if not value:
        return ""
    text = re.sub(r"<(br|/p|/li|/div|/h\d)[^>]*>", "\n", str(value), flags=re.I)
    text = _html.unescape(_TAG.sub(" ", text))
    return "\n".join(_WS.sub(" ", line).strip() for line in text.splitlines() if line.strip())


def clean(value) -> str:
    return _WS.sub(" ", _html.unescape(str(value or ""))).strip()


def label_value(text: Optional[str], labels: Iterable[str], max_len: int = 80) -> Optional[str]:
    """
    The value after the first "<label>:" in text (a line of html_text output),
    e.g. label_value("Location: Phoenix, AZ\\nType: Contract", ["location"]) -> "Phoenix, AZ".
    """
    if not text:
        return None
    for label in labels:
        m = re.search(rf"(?:^|\n|\s)(?:{label})\s*[:\-–]\s*([^\n|]+)", text, re.I)
        if m:
            value = m.group(1).strip(" .;,-–")
            # Another label on the same line ("Location: X Duration: 6 months") ends it.
            value = re.split(r"\s{2,}|\s(?=[A-Z][A-Za-z ]{2,24}:\s)|\.\s+(?=[A-Z])|,\s+(?=(?:with|and|plus|but)\s)", value)[0].strip(" .;,-–")
            if value and len(value) <= max_len:
                return value
    return None


LOCATION_LABELS = ("job location", "work location", "location\\(s\\)", "locations?", "city")
TYPE_LABELS = ("employment type", "job type", "position type", "contract type", "type of employment", "type")
PAY_LABELS = ("pay rate", "pay range", "rate", "compensation", "salary range", "salary", "pay")


def pay_from_text(text: Optional[str]):
    """(min, max, period) from a pay-labelled line of the text, else (None, None, None)."""
    if not text:
        return None, None, None
    value = label_value(text, PAY_LABELS, max_len=120)
    return parse_pay_text(value) if value else (None, None, None)


def jsonld_postings(page: Optional[str]) -> list[dict]:
    """Every schema.org JobPosting object in a page's ld+json blocks."""
    found = []
    for block in _LD_JSON.findall(page or ""):
        try:
            data = json.loads(block.strip(), strict=False)
        except ValueError:
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            item = stack.pop(0)
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("@graph"), list):
                stack.extend(item["@graph"])
            kind = item.get("@type")
            if kind == "JobPosting" or (isinstance(kind, list) and "JobPosting" in kind):
                found.append(item)
    return found


def jsonld_location(posting: dict) -> str:
    """'City, Region, Country' from a JobPosting's jobLocation (several joined by '; '); 'Remote' for TELECOMMUTE."""
    places = posting.get("jobLocation")
    places = places if isinstance(places, list) else [places] if places else []
    out = []
    for place in places:
        address = place.get("address") if isinstance(place, dict) else None
        if isinstance(address, str):
            text = clean(address)
        elif isinstance(address, dict):
            country = address.get("addressCountry")
            if isinstance(country, dict):
                country = country.get("name")
            country = _COUNTRY_NAMES.get(str(country or "").strip().upper(), country)
            parts = [clean(address.get(k)) for k in ("addressLocality", "addressRegion")]
            parts.append(clean(country))
            seen = []
            for p in parts:
                if p and p not in seen:
                    seen.append(p)
            text = ", ".join(seen)
        else:
            text = clean(place.get("name")) if isinstance(place, dict) else ""
        if text and text not in out:
            out.append(text)
    if not out and str(posting.get("jobLocationType") or "").upper() == "TELECOMMUTE":
        return "Remote"
    return "; ".join(out)


def jsonld_pay(posting: dict):
    """(min, max, period) from a JobPosting's baseSalary."""
    salary = posting.get("baseSalary")
    if not isinstance(salary, dict):
        return None, None, None
    value = salary.get("value")
    if isinstance(value, dict):
        lo = to_float(value.get("minValue") or value.get("value"))
        hi = to_float(value.get("maxValue") or value.get("value"))
        period = norm_period(value.get("unitText"))
    else:
        lo = hi = to_float(value)
        period = norm_period(salary.get("unitText"))
    if not lo and not hi:
        return None, None, None
    return lo, hi, period


def jsonld_employment(posting: dict) -> Optional[str]:
    value = posting.get("employmentType")
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value if v)
    return clean(value) or None


async def robots_allows(url: str) -> bool:
    """services.robots.allowed() (it blocks on urllib) without stalling the event loop."""
    from services import robots
    return await asyncio.to_thread(robots.allowed, url)
