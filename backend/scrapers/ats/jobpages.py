"""
A firm's own HTML job listing, for career sites with no job API (WordPress
themes, Bullhorn and Matador plugins that render server-side, ...).

The scraper reads the listing page the site shows candidates and its
numbered pages (/page/2/, ?page=2), finds the links to single postings and
takes each posting's title, location and type from its card on the listing.
When a card has no location, it opens the posting's page and reads the
schema.org JobPosting there (the markup job sites publish for search
engines). Every page is fetched only where the site's robots.txt allows it,
through the shared per-host rate limit.

A board is "<host><listing path>", e.g. "www.redfishtech.com/job-board/",
optionally "|<job path prefix>" when postings live under an unusual path
("example.com/openings/|/vacancy/"). By default a posting link is one under
/job/, /jobs/, /position(s)/, /vacancy|vacancies/ or /opening(s)/.
"""

import asyncio
import re
from typing import Optional
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from contracts.scrapers._base import parse_iso, simple_employment_type
from scrapers.ats import BoardType, register
from scrapers.ats._jobtext import (
    LOCATION_LABELS, TYPE_LABELS, clean, html_text, jsonld_employment, jsonld_location, jsonld_pay,
    jsonld_postings, label_value, pay_from_text, robots_allows,
)
from scrapers.base import ScrapedJob, ScrapeResult

_BOARD = re.compile(r"((?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.)+[a-z]{2,63})(/[^\s|]*)?(?:\|(/[A-Za-z0-9_\-/]+))?")
_JOB_DIRS = r"job|jobs|position|positions|vacancy|vacancies|opening|openings"
_SKIP_SLUGS = {"feed", "page", "category", "tag", "apply", "job-alerts", "alerts", "search", "submit", "login",
               "register", "saved", "location", "locations", "type", "types", "rss", "comments", "all"}
_GENERIC_TEXT = re.compile(r"^(read more|more info|learn more|view|view job|view & apply|view and apply|apply|apply now|"
                           r"see job details|details|job details|more|»|\W*)$", re.I)
_PAGE_PARAM = ("page", "pg", "paged", "pagenum", "_page")
_PLACE_IN_TEXT = re.compile(r"\b(?:client|role|position|company|organisation|organization|based|located)\b[^.]{0,30}?"
                            r"\bin\s+([A-Z][a-z]+(?:[ \-][A-Z][a-z]+){0,2})\b")
_ID_IN_PATH = re.compile(r"(\d{3,})")


def page_parts(board: str) -> Optional[tuple[str, str, str]]:
    m = _BOARD.fullmatch((board or "").strip())
    if not m:
        return None
    return m.group(1), m.group(2) or "/", m.group(3) or ""


def listing_url(board: str) -> str:
    host, path, _ = page_parts(board)
    return f"https://{host}{path}"


class JobPagesMixin:
    MAX_LIST_PAGES = 30
    MAX_DETAILS = 150
    TIME_BUDGET_SECONDS = 50

    def _job_path(self):
        _, _, prefix = page_parts(self.BOARD)
        if prefix:
            return re.compile(rf"^{re.escape(prefix.rstrip('/'))}/([^/]+)/?(?:([^/]+)/?)?$")
        return re.compile(rf"^/(?:[^/]+/)*?(?:{_JOB_DIRS})/([^/]+)/?(?:([^/]+)/?)?$")

    def _is_job_link(self, url: str, host: str, listing_path: str) -> bool:
        parsed = urlparse(url)
        if (parsed.hostname or "").lower() != host or parsed.path.rstrip("/") == listing_path.rstrip("/"):
            return False
        m = self._job_path().match(parsed.path)
        if not m:
            return False
        slugs = [s for s in m.groups() if s]
        return not any(s.lower() in _SKIP_SLUGS or s.lower().startswith("wp-") for s in slugs) and not (
            len(slugs) == 2 and slugs[1].lower() in _SKIP_SLUGS | {"apply", "save_job", "unsave_job"})

    async def scrape(self) -> ScrapeResult:
        host, listing_path, _ = page_parts(self.BOARD)
        start = listing_url(self.BOARD)
        if not await robots_allows(start):
            return ScrapeResult(success=False, error_message=f"robots.txt disallows {start}")
        deadline = asyncio.get_event_loop().time() + self.TIME_BUDGET_SECONDS
        queue, seen_pages, cards = [start], set(), {}
        complete = True
        while queue:
            url = queue.pop(0)
            if url in seen_pages:
                continue
            if len(seen_pages) >= self.MAX_LIST_PAGES or asyncio.get_event_loop().time() > deadline:
                complete = False
                break
            seen_pages.add(url)
            page = await self.fetch_html(url)
            for card in self.page_cards(page, url, host, listing_path):
                cards.setdefault(card["key"], card)
            for nxt in self.page_links(page, url, host, listing_path):
                if nxt not in seen_pages and nxt not in queue and await robots_allows(nxt):
                    queue.append(nxt)
        need = [c for c in cards.values() if not c.get("location")]
        for n, card in enumerate(need):
            if n >= self.MAX_DETAILS or asyncio.get_event_loop().time() > deadline:
                complete = False
                break
            if not await robots_allows(card["url"]):
                continue
            try:
                page = await self.fetch_html(card["url"])
            except Exception as e:  # one posting page failing does not fail the board
                self.logger.debug(f"posting page {card['url']} failed: {e}")
                continue
            postings = jsonld_postings(page)
            if postings:
                card["ld"] = postings[0]
            else:
                text = html_text(page)
                card["location"] = label_value(text, LOCATION_LABELS) or ""
        jobs = self.parse_all(list(cards.values()))
        return ScrapeResult(success=True, jobs=jobs, jobs_found=len(jobs), complete=complete)

    def page_links(self, page: str, base: str, host: str, listing_path: str) -> list[str]:
        """The listing's own numbered pages (/page/N/, ?page=N on the listing path)."""
        soup = BeautifulSoup(page or "", "html.parser")
        root = listing_path.rstrip("/")
        out = []
        for a in soup.find_all("a", href=True):
            url = urljoin(base, a["href"]).split("#")[0]
            parsed = urlparse(url)
            if (parsed.hostname or "").lower() != host:
                continue
            path = parsed.path.rstrip("/")
            numbered = re.fullmatch(rf"{re.escape(root)}/page/\d+", path)
            query = parse_qs(parsed.query)
            paged = path == root and any(k in query for k in _PAGE_PARAM) and len(query) <= 2
            if (numbered or paged) and url not in out:
                out.append(url)
        return out

    def page_cards(self, page: str, base: str, host: str, listing_path: str) -> list[dict]:
        soup = BeautifulSoup(page or "", "html.parser")
        for junk in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            junk.decompose()
        groups: dict[str, list] = {}
        for a in soup.find_all("a", href=True):
            url = urljoin(base, a["href"]).split("#")[0]
            if self._is_job_link(url, host, listing_path):
                groups.setdefault(urlparse(url).path.rstrip("/"), []).append((url, a))
        cards = []
        for key, anchors in groups.items():
            url, anchor = anchors[0]
            card = anchor
            node = anchor
            while node.parent is not None and node.parent.name not in ("body", "html", "[document]"):
                parent = node.parent
                keys = {urlparse(urljoin(base, x["href"])).path.rstrip("/") for x in parent.find_all("a", href=True)
                        if self._is_job_link(urljoin(base, x["href"]).split("#")[0], host, listing_path)}
                if keys - {key}:
                    break
                card = node = parent
            cards.append(self._card(key, url, anchors, card))
        return cards

    def _card(self, key: str, url: str, anchors, card) -> dict:
        heading = card.find(["h1", "h2", "h3", "h4", "h5"]) if card.name != "a" else None
        texts = [clean(a.get_text(" ")) for _, a in anchors]
        texts = [t for t in texts if t and not _GENERIC_TEXT.match(t)]
        title = clean(heading.get_text(" ")) if heading else (max(texts, key=len) if texts else "")
        location = ""
        holder = card.find(attrs={"data-location": True}) or (card if card.has_attr("data-location") else None)
        if holder is not None and clean(holder.get("data-location")):
            location = clean(holder["data-location"])
        if not location:
            node = card.find(class_=re.compile(r"locat", re.I))
            if node is not None:
                location = re.sub(r"^(job\s+)?locations?\s*:\s*", "", clean(node.get_text(" ")), flags=re.I)
        text = html_text(str(card))
        if not location:
            location = label_value(text, LOCATION_LABELS) or ""
        if not location:
            guess = _PLACE_IN_TEXT.search(text)
            location = guess.group(1) if guess else ""
        type_node = card.find(class_=re.compile(r"job[-_]?type|employment", re.I))
        emp = clean(type_node.get_text(" ")) if type_node is not None else label_value(text, TYPE_LABELS, max_len=40)
        emp = re.sub(r"^(job\s+|employment\s+)?type\s*:\s*", "", emp or "", flags=re.I) or None
        when = card.find("time")
        return {"key": key, "url": url, "title": title, "location": location, "employment": emp,
                "date": when.get("datetime") if when is not None else None, "text": text}

    def parse_job(self, raw: dict) -> Optional[ScrapedJob]:
        ld = raw.get("ld") or {}
        title = raw.get("title") or clean(ld.get("title"))
        if not title or not raw.get("url"):
            return None
        location = raw.get("location") or (jsonld_location(ld) if ld else "")
        emp = raw.get("employment") or (jsonld_employment(ld) if ld else None)
        lo, hi, period = jsonld_pay(ld) if ld else (None, None, None)
        if not lo:
            lo, hi, period = pay_from_text(raw.get("text"))
        ids = _ID_IN_PATH.findall(raw["key"])
        return ScrapedJob(
            title=title,
            location=location,
            job_url=raw["url"],
            external_job_id=ids[-1] if ids else raw["key"].rsplit("/", 1)[-1],
            job_description=self.clean_html(ld.get("description")) if ld.get("description") else None,
            posted_date=parse_iso(ld.get("datePosted") or raw.get("date")),
            employment_type=simple_employment_type(emp),
            employment_type_raw=emp,
            remote_type="remote" if location.lower().startswith("remote") else None,
            pay_rate_min=lo,
            pay_rate_max=hi,
            pay_period=period,
            salary_min=int(lo) if period == "year" and lo else None,
            salary_max=int(hi) if period == "year" and hi else None,
        )


register(BoardType(
    name="jobpages",
    mixin=JobPagesMixin,
    valid=lambda board: page_parts(board) is not None,
    start_url=listing_url,
    careers_url=listing_url,
))
