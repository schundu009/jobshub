"""
Job boards on a firm's own WordPress site, read through the two public
interfaces WordPress job sites expose:

1. The WP REST API of the post type the jobs are stored in (WP Job Manager's
   job-listings, Matador's matador-job-listings, WP Job Openings'
   awsm_job_openings, a theme's own type):

       GET https://<site>/wp-json/wp/v2/<rest_base>?per_page=100&page=N&_embed=wp:term
       (X-WP-TotalPages says how many pages)

   board "<host>[/<path>]/<rest_base>[?<query>]", e.g. "www.harnham.com/job-listings",
   "bhsg.com/jobs/job-listings" (a WordPress installed under /jobs),
   "www.excelonsolutions.com/posts?categories=5".

2. WP Job Manager's listing endpoint, the one its [jobs] shortcode pages
   call (for sites whose REST API does not list the jobs):

       POST https://<site>/jm-ajax/get_listings/   (per_page, page)
       -> {"html": "<li class=\"job_listing ...\">...", "max_num_pages": N}

   board "<host>[/<path>]/jm-ajax".

Location comes from the first of: WP Job Manager's _job_location meta, a
location/city/state/country taxonomy, a "Location:" line in the posting, a
job-location-<slug> class. Employment type and pay likewise from the
meta/taxonomies, else the posting's own "Type:" / "Pay Rate:" lines.
"""

import html as _html
import json
import re
from typing import List, Optional
from urllib.parse import urlencode

import aiohttp
from bs4 import BeautifulSoup

from contracts.scrapers._base import norm_period, parse_iso, simple_employment_type, to_float
from scrapers.ats import BoardType, register
from scrapers.ats._jobtext import (
    LOCATION_LABELS, TYPE_LABELS, clean, html_text, label_value, pay_from_text,
)
from scrapers.base import ScrapedJob, ScrapeResult, UnexpectedResponseError

_BOARD = re.compile(
    r"((?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})((?:/[A-Za-z0-9_\-]+)*)/([A-Za-z0-9_\-]{2,60})(?:\?([A-Za-z0-9_=&,\-]{1,120}))?"
)
JM_AJAX = "jm-ajax"
_FIELDS = "id,date,date_gmt,modified_gmt,link,title,content,excerpt,meta,acf,class_list,_links,_embedded"
_LOC_TAXONOMY = re.compile(r"locat|city|state|country|region|province", re.I)
_TYPE_TAXONOMY = re.compile(r"^(?!.*record).*(type|full_or_part|employment|contract)", re.I)
_EMPLOYMENT_WORD = re.compile(
    r"contract|perm|full|part|temp|hire|direct|freelance|intern|interim|fixed|time|w-?2|1099|c2c|consult|seasonal|placement",
    re.I)
_REMOTE_WORDS = {"remote", "hybrid", "onsite", "on-site", "on site", "fully remote"}
_IN_PLACE = re.compile(r"\b(?:in|at)\s+([A-Z][A-Za-z.\- ]{2,30},\s*(?:[A-Z]{2}|[A-Z][a-z]{3,}))\b")


def wp_parts(board: str) -> Optional[tuple[str, str, str, str]]:
    """'bhsg.com/jobs/job-listings' -> ('bhsg.com', '/jobs', 'job-listings', '')."""
    m = _BOARD.fullmatch((board or "").strip())
    return (m.group(1), m.group(2) or "", m.group(3), m.group(4) or "") if m else None


def list_url(board: str, page: int = 1, per_page: int = 100) -> str:
    host, path, kind, query = wp_parts(board)
    if kind == JM_AJAX:
        return f"https://{host}{path}/jm-ajax/get_listings/"
    params = f"per_page={per_page}&page={page}&_embed=wp:term&_fields={_FIELDS}"
    return f"https://{host}{path}/wp-json/wp/v2/{kind}?{params}" + (f"&{query}" if query else "")


def _terms(raw: dict) -> list[tuple[str, str]]:
    """(taxonomy, name) of every embedded term."""
    out = []
    for group in (raw.get("_embedded") or {}).get("wp:term") or []:
        for term in group if isinstance(group, list) else []:
            if isinstance(term, dict) and term.get("name"):
                out.append((str(term.get("taxonomy") or ""), clean(term["name"])))
    return out


def _class_value(classes, prefixes) -> Optional[str]:
    for c in classes or []:
        for prefix in prefixes:
            if isinstance(c, str) and c.startswith(prefix) and len(c) > len(prefix):
                return c[len(prefix):].replace("-", " ").strip().title()
    return None


def _meta_text(meta: dict, *keys) -> Optional[str]:
    for key in keys:
        value = meta.get(key)
        if isinstance(value, list):
            value = ", ".join(str(v) for v in value if v)
        if value not in (None, "", [], False):
            return clean(value)
    return None


class WordPressMixin:
    PER_PAGE = 100
    MAX_JOBS = 1500
    MAX_PAGES = 40
    PAGE_TIMEOUT_SECONDS = 45

    async def _get_json(self, url: str):
        async def read(response):
            text = (await response.text()).lstrip("﻿ \r\n\t")
            try:
                return json.loads(text), response.headers
            except ValueError:
                raise UnexpectedResponseError(f"not JSON from {url[:80]}: {text[:80]!r}")
        # 100 posts with their terms can take a WordPress site 20 s+ to render.
        return await self._request("GET", url, read, timeout=aiohttp.ClientTimeout(total=self.PAGE_TIMEOUT_SECONDS))

    async def scrape(self) -> ScrapeResult:
        _, _, kind, _ = wp_parts(self.BOARD)
        if kind == JM_AJAX:
            return await self._scrape_jm_ajax()
        raw: List[dict] = []
        total_pages = 1
        page = 1
        while page <= min(total_pages, self.MAX_PAGES) and len(raw) < self.MAX_JOBS:
            data, headers = await self._get_json(list_url(self.BOARD, page, self.PER_PAGE))
            rows = self.expect_list(data)
            raw.extend(rows)
            total_pages = int(headers.get("X-WP-TotalPages") or 1)
            if len(rows) < self.PER_PAGE:
                break
            page += 1
        live = [r for r in raw if str((r.get("meta") or {}).get("_filled") if isinstance(r.get("meta"), dict) else "") not in ("1", "True", "true")]
        jobs = self.parse_all(live)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs),
                            complete=page >= total_pages and len(raw) < self.MAX_JOBS)

    async def _scrape_jm_ajax(self) -> ScrapeResult:
        raw: List[dict] = []
        pages = 1
        page = 1
        while page <= min(pages, self.MAX_PAGES) and len(raw) < self.MAX_JOBS:
            data = await self._request(
                "POST", list_url(self.BOARD), lambda r: r.json(content_type=None),
                data={"per_page": str(self.PER_PAGE), "page": str(page), "orderby": "featured", "order": "DESC",
                      "show_pagination": "false"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            if not isinstance(data, dict) or "html" not in data:
                raise UnexpectedResponseError(f"jm-ajax answered {type(data).__name__}")
            rows = self.jm_listings(data.get("html") or "")
            raw.extend(rows)
            pages = int(data.get("max_num_pages") or 1)
            if not rows:
                break
            page += 1
        live = [r for r in raw if not r.get("expired") and not r.get("filled")]
        jobs = self.parse_all(live)
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs),
                            complete=page > pages and len(raw) < self.MAX_JOBS)

    @staticmethod
    def jm_listings(fragment: str) -> list[dict]:
        """WP Job Manager's listing <li>s -> dicts (kind "jm")."""
        soup = BeautifulSoup(fragment, "html.parser")
        out = []
        for li in soup.select("li.job_listing"):
            classes = li.get("class") or []
            link = li.find("a", href=True)
            title = li.select_one(".position h3") or li.find(["h3", "h2"])
            if not link or not title:
                continue
            post_id = next((c[5:] for c in classes if c.startswith("post-") and c[5:].isdigit()), None)
            location = li.select_one(".location")
            types = [clean(t.get_text()) for t in li.select("li.job-type, .job-type")]
            when = li.find("time")
            out.append({
                "kind": "jm", "id": post_id, "link": _html.unescape(link["href"]),
                "title": clean(title.get_text()), "location": clean(location.get_text()) if location else "",
                "types": [t for i, t in enumerate(types) if t and t not in types[:i]],
                "date": when.get("datetime") if when else None,
                "company": clean(li.select_one(".company strong").get_text()) if li.select_one(".company strong") else None,
                "expired": "status-expired" in classes, "filled": "job_position_filled" in classes,
                "classes": classes,
            })
        return out

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        if raw.get("kind") == "jm":
            return self._parse_jm(raw)
        title = clean((raw.get("title") or {}).get("rendered") if isinstance(raw.get("title"), dict) else raw.get("title"))
        link = raw.get("link")
        job_id = str(raw.get("id") or "")
        if not title or not link or not job_id:
            return None
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
        acf = raw.get("acf") if isinstance(raw.get("acf"), dict) else {}
        content = (raw.get("content") or {}).get("rendered") if isinstance(raw.get("content"), dict) else raw.get("content")
        text = html_text(content)
        terms = _terms(raw)
        location = self._location(meta, acf, terms, text, raw.get("class_list"))
        # Only terms that read as a work type (Storm2 files its sectors under job_listing_type).
        type_terms = [name for tax, name in terms if _TYPE_TAXONOMY.search(tax) and _EMPLOYMENT_WORD.search(name)]
        emp = next((c for c in (", ".join(dict.fromkeys(type_terms)), _meta_text(meta, "_job_type", "job_type"),
                                _class_value(raw.get("class_list"), ("job-type-", "matador-types-")),
                                label_value(text, TYPE_LABELS, max_len=40))
                    if c and _EMPLOYMENT_WORD.search(c)), None)
        lo, hi, period = self._pay(meta, acf, text)
        categories = [name for tax, name in terms if "categor" in tax or tax == "category"]
        return ScrapedJob(
            title=title,
            location=location,
            job_url=link,
            external_job_id=job_id,
            job_description=self.clean_html(content),
            department=categories[0] if categories else None,
            posted_date=parse_iso(raw.get("date_gmt") or raw.get("date")),
            employment_type=simple_employment_type(emp),
            employment_type_raw=emp or None,
            remote_type="remote" if location.lower().startswith(("remote", "fully remote")) else None,
            pay_rate_min=lo,
            pay_rate_max=hi,
            pay_period=period,
            salary_min=int(lo) if period == "year" and lo else None,
            salary_max=int(hi) if period == "year" and hi else None,
            extra={k: v for k, v in {"client": _meta_text(meta, "_company_name"),
                                     "source_id": _meta_text(meta, "_matador_source_id")}.items() if v},
        )

    def _location(self, meta: dict, acf: dict, terms, text: str, classes) -> str:
        value = _meta_text(meta, "_job_location", "job_location", "_location", "location")
        if value:
            return value
        for key, val in acf.items():
            if _LOC_TAXONOMY.search(str(key)) and isinstance(val, str) and clean(val):
                return clean(val)
        places = [name for tax, name in terms if _LOC_TAXONOMY.search(tax)]
        # City, then state, then country, as the taxonomies come; remote/hybrid only as a last word.
        order = {"city": 0, "locat": 1, "state": 2, "region": 3, "province": 3, "country": 4}
        ranked = sorted(((next((v for k, v in order.items() if k in tax.lower()), 5), name)
                         for tax, name in terms if _LOC_TAXONOMY.search(tax)), key=lambda x: x[0])
        names = [n for _, n in ranked]
        real = [n for i, n in enumerate(names) if n.lower() not in _REMOTE_WORDS and n not in names[:i]]
        labelled = label_value(text, LOCATION_LABELS)
        if labelled and (not real or len(real) < 2):
            return labelled
        if real:
            return ", ".join(real)
        if places:
            return places[0]
        from_class = _class_value(classes, ("job-location-", "matador-locations-", "location-"))
        if from_class:
            return from_class
        m = _IN_PLACE.search(text or "")
        return m.group(1).strip() if m else ""

    @staticmethod
    def _pay(meta: dict, acf: dict, text: str):
        lo = to_float(meta.get("_salary_min") or meta.get("_job_salary_min"))
        hi = to_float(meta.get("_salary_max") or meta.get("_job_salary_max"))
        salary = to_float(meta.get("_job_salary"))
        period = norm_period(meta.get("_job_salary_unit") or meta.get("_salary_unit"))
        if salary and not (lo or hi):
            lo = hi = salary
        if lo or hi:
            lo, hi = lo or hi, hi or lo
            period = period or ("year" if lo >= 10000 else "hour" if lo < 300 else None)
            if period:
                return lo, hi, period
        return pay_from_text(text)

    def _parse_jm(self, raw: dict) -> Optional[ScrapedJob]:
        if not raw.get("title") or not raw.get("link"):
            return None
        emp = ", ".join(raw.get("types") or []) or None
        location = raw.get("location") or _class_value(raw.get("classes"), ("job-location-",)) or ""
        return ScrapedJob(
            title=raw["title"],
            location=location,
            job_url=raw["link"],
            external_job_id=str(raw.get("id") or raw["link"]),
            posted_date=parse_iso(raw.get("date")),
            employment_type=simple_employment_type(emp),
            employment_type_raw=emp,
            remote_type="remote" if location.lower().startswith("remote") else None,
            extra={"client": raw["company"]} if raw.get("company") else {},
        )


def _careers(board: str) -> Optional[str]:
    parts = wp_parts(board)
    return f"https://{parts[0]}{parts[1]}/" if parts else None


register(BoardType(
    name="wordpress",
    mixin=WordPressMixin,
    valid=lambda board: wp_parts(board) is not None,
    start_url=lambda board: list_url(board),
    careers_url=_careers,
))
