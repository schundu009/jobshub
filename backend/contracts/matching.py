"""
Profile matching for /api/contracts/jobs (public; the caller passes the profile).

    score_job(job_title, job_skills, profile) -> (score 0-100, reasons)

profile = MatchProfile(roles=[...], skills=[...], seniority="senior")

Weights: title vs roles 55, skills overlap 35, seniority fit 10 - re-normalized
over the parts the caller provided (skills only -> skills 80 + seniority 20,
or skills 100 without a seniority).

Roles are normalized to role groups (devops, sre, platform, cloud, backend,
frontend, fullstack, software, mobile, data, ml, analyst, security, qa, pm,
design, hpc, ...), using the title patterns of services.role_profiles_data
where a profile exists, plus related groups (DevOps ~ SRE ~ Platform ~ Cloud,
Backend ~ Full Stack, Data ~ ML ~ Analyst, ...). A free-text role that is no
known group matches by phrase / token overlap.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Iterable, Optional

SENIORITY_LEVELS = ("junior", "mid", "senior", "lead", "principal")
TITLE_WEIGHT, SKILLS_WEIGHT, SENIORITY_WEIGHT = 55.0, 35.0, 10.0
SKILL_DENOMINATOR_CAP = 8  # "5 of 8 skills" - long candidate lists are not punished

_NON_ALNUM = re.compile(r"[^a-z0-9+#]+")


def norm(text: Optional[str]) -> str:
    s = str(text or "").lower()
    s = s.replace("c++", "cplusplus").replace("c#", "csharp").replace(".net", " dotnet ").replace("node.js", "nodejs")
    return " " + _NON_ALNUM.sub(" ", s).strip() + " "


# ------------------------------------------------------------------ role groups

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
    label: str  # what the caller typed ("DevOps Engineer")
    group: Optional[str]  # role group slug, None = free text
    phrase: str  # normalized input


def resolve_role(value: str) -> Optional[Role]:
    label = str(value or "").strip()
    n = norm(label.replace("-", " ").replace("_", " "))
    if not n.strip():
        return None
    groups = role_groups()
    slug = n.strip().replace(" ", "_")
    if slug in groups:
        return Role(label, slug, n)
    best = None
    for alias, grp in _ALIASES.items():
        a = norm(alias)
        if a in n and (best is None or len(a) > len(best[0])):
            best = (a, grp)
    return Role(label, best[1] if best else None, n)


def _contains(title_n: str, phrases: Iterable[str]) -> bool:
    return any(p in title_n for p in phrases)


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
    words = [w for w in role.phrase.split() if len(w) > 1 and w not in ("engineer", "developer", "senior", "sr",
                                                                         "junior", "lead", "the", "and", "of")]
    if not words:
        return 0.0
    hit = sum(1 for w in words if f" {w} " in t)
    return 0.4 * hit / len(words)


def role_title_phrases(roles: Iterable[Role]) -> list[str]:
    """Plain phrases for the SQL pre-filter (ILIKE on title) - superset of what scores."""
    groups = role_groups()
    out: set[str] = set()
    for r in roles:
        if r.phrase.strip():
            out.add(r.phrase.strip())
        if r.group and r.group in groups:
            g = groups[r.group]
            out.update(p.strip() for p in g["strong_n"] + g["weak_n"])
            for other in _RELATED.get(r.group, {}):
                if other in groups:
                    out.update(p.strip() for p in groups[other]["strong_n"])
        if not r.group:
            out.update(w for w in r.phrase.split() if len(w) > 2)
    return sorted(p for p in out if p)


# ------------------------------------------------------------------ skills

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
    aliases = {"jr": "junior", "entry": "junior", "mid-level": "mid", "intermediate": "mid", "sr": "senior",
               "staff": "lead", "architect": "principal"}
    p.seniority = aliases.get(lvl, lvl) if lvl else None
    return p


# ------------------------------------------------------------------ seniority

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


# ------------------------------------------------------------------ score

def score_job(title: str, job_skills: Optional[Iterable[str]], profile: MatchProfile) -> tuple[Optional[int], Optional[list[str]]]:
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
        job_set = {norm_skill(s) for s in (job_skills or []) if s}
        matched = [s for s in profile.skills if s in job_set or _skill_in_text(s, title_n)
                   or any(_skill_in_text(s, norm(js)) for js in job_set if len(s) > 2)]
        denom = min(len(profile.skills), SKILL_DENOMINATOR_CAP)
        frac = min(1.0, len(matched) / denom) if denom else 0.0
        parts.append((SKILLS_WEIGHT if profile.roles else 80.0, frac))
        if matched:
            shown = ", ".join(profile.skill_labels.get(s, s) for s in matched[:6])
            more = "…" if len(matched) > 6 else ""
            reasons.append(f"{len(matched)} of {len(profile.skills)} skills: {shown}{more}")

    if profile.seniority:
        fit, level = seniority_fit(title, profile.seniority)
        parts.append((SENIORITY_WEIGHT if profile.roles else 20.0, fit))
        if level and fit >= 1.0:
            reasons.append(f"{level.capitalize()} level")
        elif level and fit >= 0.6:
            reasons.append(f"{level.capitalize()} level (close to {profile.seniority})")

    total_w = sum(w for w, _ in parts)
    score = round(100.0 * sum(w * v for w, v in parts) / total_w) if total_w else 0
    return int(max(0, min(100, score))), reasons


def max_score_without_title(profile: MatchProfile) -> float:
    """Best score a job can get when its title matches no role (pre-filter is exact above this)."""
    if not profile.roles:
        return 100.0
    rest = (SKILLS_WEIGHT if profile.skills else 0.0) + (SENIORITY_WEIGHT if profile.seniority else 0.0)
    total = TITLE_WEIGHT + rest
    # an unmatched title can still score up to 0.4 via token overlap
    return 100.0 * (rest + 0.4 * TITLE_WEIGHT) / total


def max_score_without_skills(profile: MatchProfile) -> float:
    """Skills-only profile: best score when no skill matches."""
    if profile.roles or not profile.skills:
        return 100.0
    return 100.0 * (20.0 if profile.seniority else 0.0) / (80.0 + (20.0 if profile.seniority else 0.0))
