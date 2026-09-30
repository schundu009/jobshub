"""
Collabera - US postings.

Source: the server-rendered WordPress board
``https://www.collabera.com/job-search/?...&Posteddays=0&q=N`` (10 cards per page;
robots.txt allows everything). Each card has the job type and location
("Contract to Hire: Newark, California, US"), a pay range
("70.00 - 75.00 | Per Hour"), the industry and skill tags. Cards carry no
posting date, so posted_date is left empty.
Public posting URL: https://www.collabera.com/job-description/?post={id}.
Cards carry no description; ``fetch_description`` reads it from the posting
page on demand (contracts.descriptions), never during a scrape.
Verified 2026-09-29 (~440 postings).
"""

import re
from typing import Optional

from bs4 import BeautifulSoup

from scrapers.base import ScraperConfig, ScraperType
from scrapers.registry import ScraperRegistry

from ._base import STAFFING_CATEGORY, StaffingScraper, parse_pay_text

LIST_URL = "https://www.collabera.com/job-search/"
DETAIL_URL = "https://www.collabera.com/job-description/"
_POST_RE = re.compile(r"[?&]post=(\d+)")
_TOTAL_RE = re.compile(r"of\s*<span[^>]*>\s*([\d,]+)\s*</span>\s*Jobs", re.I)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(\.[\w-]+)+")


def parse_collabera_description(html: str, post_id: Optional[str] = None) -> tuple:
    """Posting page -> (description html, text) from the "Job Details" card; the
    recruiter card next to it is not read. (None, None) when the page has none,
    or when it is not this posting's page (an unknown ?post= renders a page
    without the posting's apply form)."""
    from contracts.descriptions import html_to_text
    if post_id is not None and not re.search(r"qsPostId=" + re.escape(str(post_id)) + r"(?!\d)", html or ""):
        return None, None
    soup = BeautifulSoup(html or "", "html.parser")
    body = soup.select_one("section.job_description_main .card-body.dots_point")
    if body is None:
        return None, None
    for tag in body.find_all(["script", "style", "iframe", "form"]):
        tag.decompose()
    fragment = _EMAIL_RE.sub("", body.decode_contents()).strip()
    text = html_to_text(fragment)
    if not text or len(text) < 40:
        return None, None
    return fragment, text


def fetch_description(url: str) -> tuple:
    """On-demand description for a Collabera posting URL (public page, robots allow all)."""
    from urllib.parse import parse_qs, urlparse

    from contracts.descriptions import polite_get
    u = urlparse(url or "")
    post = (parse_qs(u.query).get("post") or [""])[0]
    if not u.netloc.endswith("collabera.com") or not post.isdigit():
        return None, None
    resp = polite_get(f"{DETAIL_URL}?post={post}")
    return parse_collabera_description(resp.text, post)


def parse_collabera_listing(html: str) -> tuple[list[dict], int]:
    soup = BeautifulSoup(html, "html.parser")
    cards = []
    for card in soup.select("div.card-body"):
        link = card.find("a", href=_POST_RE)
        title = card.find("h5")
        if not link or not title:
            continue
        post_id = _POST_RE.search(link["href"]).group(1)
        job_type, location, pay = None, None, None
        for p in card.select("p.p-secondary"):
            text = p.get_text(" ", strip=True)
            if text.lower().startswith("salary range"):
                pay = text.split(":", 1)[-1].strip()
            elif ":" in text and location is None and p.find("span"):
                job_type = text.split(":", 1)[0].strip()
                location = p.find("span").get_text(" ", strip=True)
        industry = card.select_one("p.card-text")
        cards.append({
            "id": post_id,
            "url": link["href"],
            "title": title.get_text(" ", strip=True),
            "job_type": job_type,
            "location": location,
            "pay": pay,
            "industry": industry.get_text(" ", strip=True) if industry else None,
            "skills": [b.get_text(" ", strip=True) for b in card.select("ul li .badge")],
        })
    m = _TOTAL_RE.search(html)
    return cards, int(m.group(1).replace(",", "")) if m else 0


@ScraperRegistry.register(category=STAFFING_CATEGORY)
class CollaberaScraper(StaffingScraper):
    config = ScraperConfig(
        company_slug="collabera",
        company_name="Collabera",
        careers_url=LIST_URL,
        scraper_type=ScraperType.HTTP,
        request_timeout=30,
    )
    AGENCY_NAME = "Collabera"
    PAGE_SIZE = 10
    # The site's "industry" filter is the client's industry (Banking, Retail, ...),
    # not the job's function, so it is neither requested nor used as context.
    IT_SKILLS_KEYS = ("skills",)

    async def fetch_raw(self) -> list:
        raw, page, seen = [], 1, set()
        while len(raw) < self.MAX_JOBS:
            params = {"sort_by": "", "industry": "", "keyword": "", "location": "", "Posteddays": "0"}
            if page > 1:
                params["q"] = str(page)
            html = await self._http("GET", LIST_URL, params=params, expect="text")
            cards, total = parse_collabera_listing(html)
            fresh = [c for c in cards if c["id"] not in seen]
            seen.update(c["id"] for c in fresh)
            raw.extend(self.take_it(fresh))
            listed = len(seen)
            if not fresh or (total and listed >= total) or self.out_of_time():
                break
            page += 1
        return raw

    def parse_job(self, raw: dict):
        location = (raw.get("location") or "").strip()
        parts = [p.strip() for p in location.split(",")]
        if parts and parts[-1] and parts[-1].upper() not in ("US", "USA", "UNITED STATES"):
            return None
        if parts and parts[-1].upper() in ("US", "USA"):
            location = ", ".join(parts[:-1])
        lo, hi, period = parse_pay_text(raw.get("pay"))
        job_type = raw.get("job_type")
        remote = bool(job_type) and job_type.lower() == "remote"
        return self.make_job(
            title=raw.get("title"),
            location=location,
            job_url=raw.get("url"),
            external_job_id=raw.get("id"),
            # Some cards show "Remote:" where the job type usually is.
            employment_type_raw=None if remote else job_type,
            pay_min=lo, pay_max=hi, pay_period=period,
            department=raw.get("industry"),
            remote_type="remote" if remote else None,
            skills=raw.get("skills"),
        )
