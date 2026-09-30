"""
Full-time jobs (GET /api/jobs) helpers for the cariara.com/jobs/firm page.

    derive_work_type(title, location, description) -> "remote" | "hybrid" | "onsite" | None
    build_profile(roles, skills, seniority) -> MatchProfile
    score_job(title, tech_stack, profile) -> (match_score 0-100, match_reasons)
    resolve_location(value) -> city aliases for a metro label/key, else None (free text)
    search_terms(q) -> [(token, whole_word)]
    ttl_cache: in-process cache for scored candidate lists (clear_caches() resets it)

Skills-based matching follows the contracts page's approach (backend/contracts/
matching.py) but is a separate copy on purpose: full-time and contract jobs are
maintained apart. Weights: title vs roles 55, skills overlap 35, seniority 10 -
re-normalized over the parts the caller gave (skills only -> 80/20).

No model imports at module level: models.py calls derive_work_type from a
save hook.
"""
from __future__ import annotations

import html
import re
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Optional

# ================================================================== work type

WORK_TYPES = ("remote", "hybrid", "onsite")

_WT_HYBRID_SHORT = re.compile(r"\bhybrid\b(?!\s+cloud)", re.I)
_WT_REMOTE_LOC = re.compile(r"(?<![\w])(remote|anywhere|work from home|wfh|distributed|telecommute)(?![\w])", re.I)
# Titles: "distributed" / "anywhere" there are about the work, not the place.
_WT_REMOTE_TITLE = re.compile(r"(?<![\w])(remote|work from home|wfh)(?![\w])", re.I)
_WT_HYBRID_DESC = re.compile(
    r"\bhybrid\s+(?:role|position|work|working|schedule|model|arrangement|environment|opportunity|setup|policy|"
    r"workplace|team|job)\b"
    r"|\b(?:is|are|be)\s+(?:a\s+|fully\s+)?hybrid\b|\bhybrid\s*\(|\(hybrid\)|\bhybrid\s*[-–:,]\s*\w"
    r"|\b(?:\d|two|three|four)\s+days?\s+(?:a|per)\s+week\s+in\s+(?:the\s+|our\s+)?office\b"
    r"|\b(?:in[- ]office|onsite|on-site)\s+(?:\d|two|three|four)\s+days?\b",
    re.I,
)
_WT_REMOTE_DESC = re.compile(
    r"\b(fully remote|100% remote|remote[- ]first|remote position|remote role|remote opportunity|remote-friendly|"
    r"work remotely|working remotely|this (?:role|position|job) is remote|is a remote|remote within|remote in the|"
    r"remote \(|remote,? (?:us|usa|united states|canada|uk)\b)",
    re.I,
)
_WT_ONSITE_DESC = re.compile(r"\b(on-?site|in[- ]office|in[- ]person|office[- ]based)\b", re.I)
_UNSPECIFIED_LOC = re.compile(
    r"^(?:remote|anywhere|worldwide|global|distributed|multiple locations|various locations|flexible|tbd|n/a|-|—)?$",
    re.I,
)
_TAG = re.compile(r"<[^>]+>")
WORK_TYPE_DESC_CHARS = 20000


def _plain(text: Optional[str], limit: int = WORK_TYPE_DESC_CHARS) -> str:
    if not text:
        return ""
    t = text[: limit * 2]
    if "&" in t:
        t = html.unescape(t)
    if "<" in t:
        t = _TAG.sub(" ", t)
    return t[:limit]


def derive_work_type(title: Optional[str], location: Optional[str], description: Optional[str] = None) -> Optional[str]:
    """remote / hybrid / onsite from location, title and description keywords; else onsite for a concrete
    location, else None."""
    title = title or ""
    loc = (location or "").strip()
    if _WT_HYBRID_SHORT.search(loc) or _WT_HYBRID_SHORT.search(title):
        return "hybrid"
    if _WT_REMOTE_LOC.search(loc) or _WT_REMOTE_TITLE.search(title):
        return "remote"
    desc = _plain(description)
    if desc:
        if _WT_HYBRID_DESC.search(desc):
            return "hybrid"
        if _WT_REMOTE_DESC.search(desc):
            return "remote"
        if _WT_ONSITE_DESC.search(desc):
            return "onsite"
    if loc and not _UNSPECIFIED_LOC.match(loc):
        return "onsite"
    return None


# ================================================================== employment type

EMPLOYMENT_TYPES = ("full_time", "part_time", "internship", "temporary")
# filter value -> stored values it covers (NULL counts as full_time; the route adds that)
EMPLOYMENT_ALIASES = {
    "full_time": ("full_time", "fulltime", "full-time", "permanent"),
    "part_time": ("part_time", "parttime", "part-time"),
    "internship": ("internship", "intern"),
    "temporary": ("temporary", "temp", "seasonal"),
}


def normalize_employment(value: Optional[str]) -> str:
    t = re.sub(r"[\s-]+", "_", (value or "").strip().lower())
    if not t or t in ("fulltime", "permanent"):
        return "full_time"
    if t == "parttime":
        return "part_time"
    if t == "intern":
        return "internship"
    if t in ("temp", "seasonal"):
        return "temporary"
    return t


# ================================================================== location

# key -> (label, aliases); mirrors US_METROS in the page's firmQuery.ts
US_METROS: dict[str, tuple[str, tuple[str, ...]]] = {
    "sf": ("San Francisco Bay Area", ("san francisco", "sf bay area", "bay area", "south san francisco", "palo alto",
                                      "mountain view", "menlo park", "sunnyvale", "san jose", "santa clara",
                                      "cupertino", "redwood city", "san mateo", "foster city", "oakland", "berkeley")),
    "nyc": ("New York City", ("new york", "nyc", "manhattan", "brooklyn", "jersey city")),
    "seattle": ("Seattle area", ("seattle", "bellevue", "redmond", "kirkland")),
    "la": ("Los Angeles", ("los angeles", "santa monica", "pasadena", "irvine", "culver city")),
    "austin": ("Austin", ("austin",)),
    "boston": ("Boston", ("boston", "cambridge, ma", "somerville")),
    "chicago": ("Chicago", ("chicago",)),
    "denver": ("Denver / Boulder", ("denver", "boulder")),
}
_METRO_BY_NAME = {}
for _k, (_label, _aliases) in US_METROS.items():
    _METRO_BY_NAME[_k] = _aliases
    _METRO_BY_NAME[_label.lower()] = _aliases


def resolve_location(value: Optional[str]) -> Optional[tuple[str, ...]]:
    """City aliases for a metro label or key ("San Francisco Bay Area", "sf"); None = free text."""
    return _METRO_BY_NAME.get(re.sub(r"\s+", " ", (value or "").strip().lower()))


# ================================================================== search

_TOKEN_TRIM = re.compile(r"^[^\w+#.]+|[^\w+#]+$")


def search_terms(q: Optional[str]) -> list[tuple[str, bool]]:
    """Lower-cased words of q, each with whole_word=True when it is short (<= 3 letters)."""
    out: list[tuple[str, bool]] = []
    for raw in (q or "").lower().split()[:12]:
        tok = _TOKEN_TRIM.sub("", raw)
        if tok and tok not in (t for t, _ in out):
            out.append((tok, len(tok) <= 3))
    return out


def word_regex(token: str) -> str:
    """Case-folded whole-word pattern valid in both Python re (SQLite REGEXP) and PostgreSQL ARE."""
    return f"(^|[^a-z0-9]){re.escape(token.lower())}([^a-z0-9]|$)"


# ================================================================== role groups

SENIORITY_LEVELS = ("junior", "mid", "senior", "lead", "principal")
TITLE_WEIGHT, SKILLS_WEIGHT, SENIORITY_WEIGHT = 55.0, 35.0, 10.0
SKILLS_ONLY_WEIGHT, SENIORITY_ONLY_WEIGHT = 80.0, 20.0
SKILL_DENOMINATOR_CAP = 8  # "5 of 8 skills" - long candidate lists are not punished

_NON_ALNUM = re.compile(r"[^a-z0-9+#]+")


def norm(text: Optional[str]) -> str:
    s = str(text or "").lower()
    s = s.replace("c++", "cplusplus").replace("c#", "csharp").replace(".net", " dotnet ").replace("node.js", "nodejs")
    return " " + _NON_ALNUM.sub(" ", s).strip() + " "


_EXTRA_GROUPS: dict[str, dict] = {
    "cloud": {"name": "Cloud Engineer",
              "strong": ["cloud engineer", "cloud architect", "cloud developer", "cloud administrator", "aws engineer",
                         "azure engineer", "gcp engineer", "aws architect", "azure architect", "gcp architect",
                         "cloud infrastructure", "cloud platform", "cloud operations"],
              "weak": ["devops", "platform engineer", "infrastructure engineer", "solutions architect", "cloud"]},
    "software": {"name": "Software Engineer",
                 "strong": ["software engineer", "software developer", "software development engineer", "developer",
                            "programmer", "application developer", "sde", "swe"],
                 "weak": ["engineer", "architect", "tech lead", "technical lead"]},
    "qa": {"name": "QA Engineer",
           "strong": ["qa", "quality assurance", "test engineer", "sdet", "tester", "test automation", "test analyst",
                      "automation engineer", "test lead"],
           "weak": ["quality engineer", "validation engineer", "uat"]},
    "pm": {"name": "Product / Program Manager",
           "strong": ["product manager", "product owner", "program manager", "project manager", "scrum master",
                      "technical program manager", "delivery manager", "tpm", "agile coach", "release manager"],
           "weak": ["business analyst", "project lead", "pmo"]},
    "design": {"name": "Product Designer",
               "strong": ["ux", "ui designer", "ui ux", "product designer", "user experience", "interaction designer",
                          "visual designer", "ux researcher", "user interface"],
               "weak": ["web designer", "designer"]},
    "analyst": {"name": "Business / Data Analyst",
                "strong": ["business analyst", "systems analyst", "system analyst", "data analyst", "bi analyst",
                           "business systems analyst", "reporting analyst", "business intelligence analyst"],
                "weak": ["analyst"]},
    "network": {"name": "Network / Systems Engineer",
                "strong": ["network engineer", "network administrator", "network architect", "systems administrator",
                           "system administrator", "sysadmin", "windows administrator", "linux administrator",
                           "database administrator", "dba", "systems engineer"],
                "weak": ["network", "infrastructure engineer", "administrator"]},
    "support": {"name": "IT Support",
                "strong": ["help desk", "helpdesk", "service desk", "desktop support", "it support", "technical support",
                           "support technician", "it technician"],
                "weak": ["support engineer", "support analyst", "technician"]},
    "embedded": {"name": "Embedded / Firmware Engineer",
                 "strong": ["embedded", "firmware", "fpga", "asic", "hardware engineer"],
                 "weak": ["electrical engineer", "rtos"]},
}

_RELATED: dict[str, dict[str, float]] = {
    "devops": {"sre": 0.8, "platform": 0.8, "cloud": 0.8, "security": 0.4, "network": 0.4, "hpc": 0.5},
    "sre": {"devops": 0.8, "platform": 0.8, "cloud": 0.7, "network": 0.4},
    "platform": {"devops": 0.8, "sre": 0.8, "cloud": 0.7, "backend": 0.5, "hpc": 0.5},
    "cloud": {"devops": 0.8, "platform": 0.7, "sre": 0.7, "cloud_architect": 0.9, "network": 0.4},
    "cloud_architect": {"cloud": 0.9, "devops": 0.6, "platform": 0.6},
    "backend": {"fullstack": 0.8, "software": 0.7, "platform": 0.5, "data": 0.4},
    "frontend": {"fullstack": 0.8, "software": 0.6, "mobile": 0.4, "design": 0.3},
    "fullstack": {"backend": 0.8, "frontend": 0.8, "software": 0.7},
    "software": {"backend": 0.8, "fullstack": 0.8, "frontend": 0.7, "mobile": 0.6, "embedded": 0.4, "qa": 0.3},
    "mobile": {"frontend": 0.4, "software": 0.6},
    "data": {"ml": 0.6, "analyst": 0.5, "backend": 0.4},
    "ml": {"data": 0.6, "hpc": 0.5},
    "analyst": {"data": 0.5, "pm": 0.4},
    "security": {"devops": 0.4, "network": 0.4},
    "qa": {"software": 0.3},
    "pm": {"analyst": 0.4},
    "design": {"frontend": 0.3},
    "hpc": {"ml": 0.5, "platform": 0.5, "devops": 0.4},
    "network": {"support": 0.4, "devops": 0.4, "cloud": 0.4},
    "support": {"network": 0.4},
    "embedded": {"software": 0.4},
}

# input word/phrase -> group (longest alias contained in the role string wins)
_ALIASES: dict[str, str] = {
    "devops": "devops", "dev ops": "devops", "devsecops": "security", "sre": "sre", "site reliability": "sre",
    "reliability": "sre", "platform": "platform", "cloud architect": "cloud_architect",
    "solutions architect": "cloud_architect", "cloud": "cloud", "aws": "cloud", "azure": "cloud", "gcp": "cloud",
    "infrastructure": "devops", "backend": "backend", "back end": "backend", "api": "backend",
    "frontend": "frontend", "front end": "frontend", "ui engineer": "frontend", "react": "frontend",
    "web developer": "frontend", "fullstack": "fullstack", "full stack": "fullstack", "software": "software",
    "developer": "software", "programmer": "software", "swe": "software", "sde": "software", "mobile": "mobile",
    "ios": "mobile", "android": "mobile", "data engineer": "data", "data engineering": "data", "etl": "data",
    "data": "data", "analytics engineer": "data", "ml": "ml", "machine learning": "ml", "ai": "ml",
    "data scientist": "ml", "data science": "ml", "mlops": "ml", "analyst": "analyst",
    "business analyst": "analyst", "data analyst": "analyst", "bi": "analyst", "security": "security",
    "cybersecurity": "security", "cyber": "security", "appsec": "security", "infosec": "security", "qa": "qa",
    "quality assurance": "qa", "test": "qa", "tester": "qa", "sdet": "qa", "pm": "pm", "product manager": "pm",
    "project manager": "pm", "program manager": "pm", "scrum": "pm", "scrum master": "pm", "product owner": "pm",
    "tpm": "pm", "design": "design", "designer": "design", "ux": "design", "ui": "design", "hpc": "hpc",
    "gpu": "hpc", "network": "network", "sysadmin": "network", "systems administrator": "network",
    "dba": "network", "database administrator": "network", "help desk": "support", "helpdesk": "support",
    "desktop support": "support", "it support": "support", "embedded": "embedded", "firmware": "embedded",
}


@lru_cache(maxsize=1)
def role_groups() -> dict[str, dict]:
    groups: dict[str, dict] = {}
    try:
        from services.role_profiles_data import ROLE_PROFILES
        for p in ROLE_PROFILES:
            tp = p.get("title_patterns") or {}
            groups[p["slug"]] = {"name": p.get("name") or p["slug"],
                                 "strong": list(tp.get("strong_match") or []),
                                 "weak": list(tp.get("weak_match") or [])}
    except Exception:  # pragma: no cover
        pass
    for slug, g in _EXTRA_GROUPS.items():
        if slug in groups:
            groups[slug]["strong"] += g["strong"]
            groups[slug]["weak"] += g["weak"]
        else:
            groups[slug] = {k: list(v) if isinstance(v, list) else v for k, v in g.items()}
    for g in groups.values():
        g["strong_n"] = sorted({norm(x) for x in g["strong"] if x.strip()}, key=len, reverse=True)
        g["weak_n"] = sorted({norm(x) for x in g["weak"] if x.strip()}, key=len, reverse=True)
    return groups


@dataclass(frozen=True)
class Role:
    label: str  # shown in reasons ("Backend Engineer" for the slug "backend", else as typed)
    group: Optional[str]  # role group slug, None = free text
    phrase: str  # normalized input
    raw: str = ""  # lower-cased input, for the SQL pre-filter


def resolve_role(value: str) -> Optional[Role]:
    label = str(value or "").strip()
    n = norm(label.replace("-", " ").replace("_", " "))
    if not n.strip():
        return None
    groups = role_groups()
    slug = n.strip().replace(" ", "_")
    if slug in groups:
        return Role(groups[slug].get("name") or label, slug, n, label.lower())
    best = None
    for alias, grp in _ALIASES.items():
        a = norm(alias)
        if a in n and (best is None or len(a) > len(best[0])):
            best = (a, grp)
    return Role(label, best[1] if best else None, n, label.lower())


def _contains(title_n: str, phrases: Iterable[str]) -> bool:
    return any(p in title_n for p in phrases)


_ROLE_STOP = ("engineer", "developer", "senior", "sr", "junior", "lead", "the", "and", "of")


def title_similarity(title: str, role: Role) -> float:
    t = norm(title)
    groups = role_groups()
    if role.phrase.strip() and role.phrase in t:
        return 1.0
    if role.group and role.group in groups:
        g = groups[role.group]
        if _contains(t, g["strong_n"]):
            return 1.0
        best = 0.0
        for other, w in _RELATED.get(role.group, {}).items():
            og = groups.get(other)
            if og and _contains(t, og["strong_n"]):
                best = max(best, 0.9 * w)
        if _contains(t, g["weak_n"]):
            best = max(best, 0.6)
        if best:
            return best
    # free text / no group hit: token overlap with the role words
    words = [w for w in role.phrase.split() if len(w) > 1 and w not in _ROLE_STOP]
    if not words:
        return 0.0
    hit = sum(1 for w in words if f" {w} " in t)
    return 0.4 * hit / len(words)


_SQL_WORD = re.compile(r"[a-z0-9+#]+")


def _word_set(phrase: str) -> tuple[str, ...]:
    return tuple(sorted(set(_SQL_WORD.findall(phrase.lower()))))


def role_title_word_sets(roles: Iterable[Role]) -> list[tuple[str, ...]]:
    """Word sets for the SQL title pre-filter: a title that scores contains every word of at least one set.

    A superset of what title_similarity accepts (phrases are split into words, so "full stack" also
    finds "Full-Stack"), reduced so no set contains another.
    """
    groups = role_groups()
    phrases: set[str] = set()
    for r in roles:
        if r.raw.strip():
            phrases.add(r.raw.replace("-", " ").replace("_", " "))
        if r.group and r.group in groups:
            g = groups[r.group]
            phrases.update(g["strong"] + g["weak"])
            for other in _RELATED.get(r.group, {}):
                if other in groups:
                    phrases.update(groups[other]["strong"])
        if not r.group:
            # free text scores by token overlap: any one word is enough
            phrases.update(w for w in r.phrase.split() if len(w) > 2 and w not in _ROLE_STOP)
    sets = {s for s in (_word_set(p) for p in phrases) if s}
    # the normalized forms (c++ -> cplusplus) never appear in raw titles; use the raw spelling
    sets = {tuple(sorted({{"cplusplus": "c++", "csharp": "c#", "dotnet": ".net", "nodejs": "node"}.get(w, w)
                          for w in s})) for s in sets}
    ordered = sorted(sets, key=len)
    kept: list[tuple[str, ...]] = []
    for s in ordered:
        if not any(set(k) <= set(s) for k in kept):
            kept.append(s)
    return kept


# ================================================================== skills

_SKILL_ALIASES = {
    "k8s": "kubernetes", "kube": "kubernetes", "golang": "go", "js": "javascript", "ts": "typescript",
    "postgres": "postgresql", "psql": "postgresql", "node": "node.js", "nodejs": "node.js", "reactjs": "react",
    "react.js": "react", "vuejs": "vue", "vue.js": "vue", "angularjs": "angular", "amazon web services": "aws",
    "google cloud": "gcp", "google cloud platform": "gcp", "microsoft azure": "azure", "ci cd": "ci/cd",
    "cicd": "ci/cd", "tf": "terraform", "ml": "machine learning", "dotnet": ".net", "c sharp": "c#",
    "csharp": "c#", "cpp": "c++", "py": "python", "springboot": "spring boot", "gh actions": "github actions",
    "mssql": "sql server", "ms sql": "sql server", "tsql": "sql", "t-sql": "sql", "pl/sql": "plsql",
    "powerbi": "power bi", "sfdc": "salesforce", "snow": "servicenow", "gke": "kubernetes", "eks": "kubernetes",
    "aks": "kubernetes", "iac": "terraform",
}


def norm_skill(value) -> str:
    s = re.sub(r"\s+", " ", str(value or "").strip().lower())
    s = s.strip(" .,;")
    return _SKILL_ALIASES.get(s, s)


def skill_spellings(skill: str) -> list[str]:
    """A normalized skill and the aliases that map to it (for the SQL pre-filter)."""
    return sorted({skill, *(a for a, v in _SKILL_ALIASES.items() if v == skill)})


def _skill_in_text(skill: str, text_n: str) -> bool:
    n = norm(skill)
    return bool(n.strip()) and n in text_n


@dataclass
class MatchProfile:
    roles: list[Role] = field(default_factory=list)
    skills: list[str] = field(default_factory=list)  # normalized, unique, in caller order
    skill_labels: dict[str, str] = field(default_factory=dict)  # normalized -> as typed
    seniority: Optional[str] = None

    @property
    def active(self) -> bool:
        return bool(self.roles or self.skills)


_SENIORITY_ALIASES = {"jr": "junior", "entry": "junior", "entry level": "junior", "entry-level": "junior",
                      "mid-level": "mid", "mid level": "mid", "intermediate": "mid", "sr": "senior",
                      "staff": "lead", "architect": "principal"}


def build_profile(roles: Optional[str], skills: Optional[str], seniority: Optional[str]) -> MatchProfile:
    p = MatchProfile()
    for part in (roles or "").split(","):
        r = resolve_role(part)
        if r and r.phrase not in {x.phrase for x in p.roles}:
            p.roles.append(r)
    for part in (skills or "").split(","):
        s = norm_skill(part)
        if s and s not in p.skill_labels:
            p.skills.append(s)
            p.skill_labels[s] = part.strip()
    p.roles, p.skills = p.roles[:20], p.skills[:50]
    lvl = (seniority or "").strip().lower() or None
    p.seniority = _SENIORITY_ALIASES.get(lvl, lvl) if lvl else None
    return p


# ================================================================== seniority

_LEVEL_RX = [
    ("principal", re.compile(r"\b(principal|distinguished|fellow|chief|director|vp|head of)\b", re.I)),
    ("lead", re.compile(r"\b(lead|staff|manager|architect)\b", re.I)),
    ("senior", re.compile(r"\b(senior|sr|iii|iv|level 3|level iii|l3|l4|expert|advanced)\b", re.I)),
    ("junior", re.compile(r"\b(junior|jr|entry|entry[- ]level|associate|graduate|intern|apprentice|trainee|i|level 1|l1)\b", re.I)),
    ("mid", re.compile(r"\b(mid|mid[- ]level|intermediate|ii|level 2|l2)\b", re.I)),
]


def title_level(title: str) -> Optional[str]:
    t = str(title or "").replace(".", " ")
    for level, rx in _LEVEL_RX:
        if rx.search(t):
            return level
    return None


def seniority_fit(title: str, wanted: str) -> tuple[float, Optional[str]]:
    level = title_level(title)
    if wanted not in SENIORITY_LEVELS:
        return 0.5, level
    if level is None:
        return 0.7, None  # unmarked titles are usually mid/senior
    d = abs(SENIORITY_LEVELS.index(level) - SENIORITY_LEVELS.index(wanted))
    return (1.0, 0.6, 0.25, 0.0, 0.0)[d], level


# ================================================================== score

def score_job(title: str, job_skills: Optional[Iterable[str]], profile: MatchProfile) -> tuple[Optional[int], Optional[list[str]]]:
    """(match_score 0-100, reasons) from the title, the job's tech stack (+ title words) and seniority."""
    if not profile.active:
        return None, None
    parts: list[tuple[float, float]] = []  # (weight, 0..1)
    reasons: list[str] = []

    if profile.roles:
        best, best_role = 0.0, None
        for r in profile.roles:
            sim = title_similarity(title, r)
            if sim > best:
                best, best_role = sim, r
        parts.append((TITLE_WEIGHT, best))
        if best_role is not None and best >= 0.9:
            reasons.append(f"Title matches {best_role.label}")
        elif best_role is not None and best >= 0.5:
            reasons.append(f"Title related to {best_role.label}")

    if profile.skills:
        title_n = norm(title)
        job_set = {norm_skill(s) for s in (job_skills or []) if isinstance(s, str) and s}
        job_norms = [norm(js) for js in job_set]
        matched = [s for s in profile.skills if s in job_set or _skill_in_text(s, title_n)
                   or (len(s) > 2 and any(_skill_in_text(s, jn) for jn in job_norms))]
        denom = min(len(profile.skills), SKILL_DENOMINATOR_CAP)
        frac = min(1.0, len(matched) / denom) if denom else 0.0
        parts.append((SKILLS_WEIGHT if profile.roles else SKILLS_ONLY_WEIGHT, frac))
        if matched:
            shown = ", ".join(profile.skill_labels.get(s, s) for s in matched[:6])
            more = ", …" if len(matched) > 6 else ""
            reasons.append(f"{len(matched)} of {len(profile.skills)} skills: {shown}{more}")

    if profile.seniority:
        fit, level = seniority_fit(title, profile.seniority)
        parts.append((SENIORITY_WEIGHT if profile.roles else SENIORITY_ONLY_WEIGHT, fit))
        if level and fit >= 1.0:
            reasons.append(f"{level.capitalize()} level")
        elif level and fit >= 0.6:
            reasons.append(f"{level.capitalize()} level (close to {profile.seniority})")

    total_w = sum(w for w, _ in parts)
    score = round(100.0 * sum(w * v for w, v in parts) / total_w) if total_w else 0
    return int(max(0, min(100, score))), reasons


def max_score_without_skills(profile: MatchProfile) -> float:
    """Skills-only profile: the best score a job matching none of the skills can reach."""
    if profile.roles or not profile.skills:
        return 100.0
    sen = SENIORITY_ONLY_WEIGHT if profile.seniority else 0.0
    return 100.0 * sen / (SKILLS_ONLY_WEIGHT + sen)


# ================================================================== in-process TTL cache

class TTLCache:
    """Small thread-safe LRU with per-entry expiry (L1 in front of Redis)."""

    def __init__(self, maxsize: int = 128, ttl: float = 300.0):
        self.maxsize, self.ttl = maxsize, ttl
        self._data: "OrderedDict[str, tuple[float, object]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            hit = self._data.get(key)
            if hit is None:
                return None
            expires, value = hit
            if expires < time.monotonic():
                self._data.pop(key, None)
                return None
            self._data.move_to_end(key)
            return value

    def set(self, key: str, value, ttl: Optional[float] = None) -> None:
        with self._lock:
            self._data[key] = (time.monotonic() + (ttl or self.ttl), value)
            self._data.move_to_end(key)
            while len(self._data) > self.maxsize:
                self._data.popitem(last=False)

    def clear(self) -> None:
        with self._lock:
            self._data.clear()


ttl_cache = TTLCache()


def clear_caches() -> None:
    ttl_cache.clear()
