"""
Contract job classifier: employment type, tax terms, pay rate, contract length,
visa terms and US location - pure regex functions, cheap enough to run on every save.

The full-time pipeline imports only detect_employment_type() from here, to
route contract postings into contract_jobs.

    classify(title, description, location, raw) -> dict

``raw`` carries structured ATS/scraper fields when available:
    employment_type_raw, employment_type, pay_rate_min, pay_rate_max,
    pay_period, salary_min, salary_max, extra (dict)

Structured ATS fields win over text; the title wins over the description
(except that an explicit contract marker in the title beats an ATS
"Full-time" default, which many boards set lazily).
"""
from __future__ import annotations

import html as _html
import math
import re
from datetime import datetime
from typing import Any, Optional

EMPLOYMENT_TYPES = (
    "full_time", "part_time", "contract", "contract_to_hire",
    "temporary", "internship", "freelance",
)
CONTRACT_TYPES = ("contract", "contract_to_hire", "temporary", "freelance")
TAX_TERMS = ("w2", "c2c", "1099")
VISA_TERMS = (
    "usc_only", "usc_gc_only", "gc_ead_ok", "h1b_ok", "h1b_transfer",
    "no_c2c", "no_sponsorship", "sponsorship_available", "security_clearance",
)
PAY_PERIODS = ("hour", "day", "week", "month", "year")

# Plausible bounds per pay period (reject parse nonsense).
_PAY_BOUNDS = {
    "hour": (7.25, 500.0),
    "day": (58.0, 4000.0),
    "week": (290.0, 20000.0),
    "month": (1200.0, 170000.0),
    "year": (15000.0, 2000000.0),
}

I = re.IGNORECASE


# --------------------------------------------------------------------------- text

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def to_text(value: Optional[str], limit: int = 60000) -> str:
    """HTML/entities -> plain single-spaced text (bounded for regex cost)."""
    if not value:
        return ""
    s = str(value)
    if "&lt;" in s or "&amp;" in s or "&gt;" in s:
        s = _html.unescape(s)
    s = _TAG_RE.sub(" ", s)
    s = _html.unescape(s)
    s = s.replace(" ", " ").replace("‑", "-")
    s = _WS_RE.sub(" ", s).strip()
    return s[:limit]


_NEG_BEFORE = re.compile(
    r"\b(not|no|non|never|isn'?t|aren'?t|without|nor|neither)\b[\w\s,/-]{0,12}$", I
)


def _negated(text: str, start: int, window: int = 30) -> bool:
    return bool(_NEG_BEFORE.search(text[max(0, start - window):start]))


# ---------------------------------------------------------------- employment type

def _norm_raw(value: str) -> str:
    s = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", str(value))  # FullTime -> Full Time
    s = s.lower().replace("_", " ").replace("-", " ")
    return _WS_RE.sub(" ", s).strip()


_RAW_RULES = [
    ("contract_to_hire", re.compile(r"\b(contract to (hire|perm\w*)|c2h|temp to (hire|perm\w*)|contract with (the )?possibility)", I)),
    ("internship", re.compile(r"\b(intern|internship|interns|co op|coop|apprentice(ship)?|trainee)\b", I)),
    ("freelance", re.compile(r"\b(freelance|freelancer|1099|independent contractor)\b", I)),
    ("contract", re.compile(r"\b(contract|contractor|contractual|c2c|corp to corp|consultant|consulting)\b", I)),
    # "Fixed Term" / "Seasonal" labels are direct-hire temps (retail), not staffing contracts
    ("temporary", re.compile(r"\b(temporary|temp|seasonal|casual|per diem|prn|fixed term)\b", I)),
    ("part_time", re.compile(r"\b(part time|parttime|pt)\b", I)),
    ("full_time", re.compile(r"\b(full time|fulltime|ft|permanent|regular|fte|salaried|employee)\b", I)),
]


def map_employment_type_raw(value: Optional[str]) -> Optional[str]:
    """ATS employment-type string -> canonical code (None when unmappable)."""
    if not value:
        return None
    if isinstance(value, (list, tuple)):
        value = " ".join(str(v) for v in value if v)
    s = _norm_raw(value)
    if not s:
        return None
    if s in EMPLOYMENT_TYPES or s.replace(" ", "_") in EMPLOYMENT_TYPES:
        return s.replace(" ", "_")
    for code, rx in _RAW_RULES:
        if rx.search(s):
            return code
    return None


# Words after "contract"/"contracts" that describe contract *work*, not the job's terms.
_CONTRACT_ROLE_NOUNS = (
    r"manager|management|managers|specialist|specialists|administrator|administration|admin|"
    r"analyst|negotiator|negotiation|negotiations|officer|lawyer|counsel|coordinator|compliance|"
    r"lifecycle|life cycle|review|reviewer|director|paralegal|manufacturing|research|"
    r"manufacturer|operations|professional|owner|drafting|closeout|pricing|accountant|"
    r"accounting|lead|supervisor|associate|clerk|processor|strategy|strategist|and|&|"
    r"sales|vehicle|logistics|engineer(?:ing)? manager|of|law"
)
_CONTRACTOR_ROLE_NOUNS = (
    r"management|manager|relations|liaison|safety|oversight|compliance|onboarding|"
    r"coordinator|program|payments?|accounting|recruiting operations"
)

_TITLE_C2H = re.compile(
    r"\b(contract[- ]?to[- ]?(hire|perm(anent)?)|c2h|temp[- ]?to[- ]?(hire|perm(anent)?)|cth)\b", I)
_TITLE_INTERN = re.compile(r"\b(intern|internship|co-?op)\b(?!al)", I)
_TITLE_FREELANCE = re.compile(r"\b(freelance|freelancer)\b", I)
_TITLE_CONTRACT = re.compile(
    r"(?<!government )(?<!federal )(?<!vendor )(?<!customer )(?<!sales )(?<!commercial )"
    r"\bcontract(?:or)?\b(?!s)(?![- ](?:" + _CONTRACT_ROLE_NOUNS + r")\b)", I)
_TITLE_CONTRACTOR_BAD = re.compile(
    r"\b(government|defense|federal|general|electrical|mechanical)\s+contractors?\b|"
    r"\bcontractors?\s+(" + _CONTRACTOR_ROLE_NOUNS + r")\b", I)
_TITLE_TEMP = re.compile(r"\b(temp|temporary|seasonal)\b(?![- ]?(to[- ])?(hire|perm))", I)
_TITLE_PART = re.compile(r"\bpart[- ]?time\b", I)
_TITLE_FULL = re.compile(r"\bfull[- ]?time\b", I)
_TITLE_1099 = re.compile(r"\(\s*1099\s*\)|\b1099\s+(contract|contractor|only|role|position|basis)\b|\b(on|via)\s+1099\b|\bw-?2\s*/\s*1099\b|\b1099\s*/\s*(w-?2|c2c)\b", I)


# Phrases where "contract" names the work, not the job's terms: blockchain
# ("Smart Contract Engineer"), procurement / legal roles ("Contract Manager",
# "Contracts Systems Analyst", "Government Contracts"), CLM tooling.
_CONTRACT_WORK_PHRASES = re.compile(
    r"\bsmart[- ]contracts?\b(?:[- ](?:engineer|developer|auditor|security|programmer)s?)?|"
    r"\b(?:government|federal|defen[cs]e|dod|vendor|customer|client|supplier|commercial|sales|prime|sub)[- ]contracts?\b|"
    r"\bcontracts?[- ](?:management|manager|managers|administrator|administration|admin|specialist|analyst|"
    r"negotiat\w*|review\w*|lifecycle|life[- ]cycle|systems?|compliance|attorney|counsel|lawyer|officer|"
    r"coordinator|paralegal|drafting|closeout|pricing|operations)\b|"
    r"\bclm\b(?:[- ](?:contract|contracts))?|\bcontract lifecycle management\b", I)


def strip_contract_work(text: str) -> str:
    """Blank out phrases where "contract" is the subject of the work, not the terms."""
    return _CONTRACT_WORK_PHRASES.sub(" ", text) if text else (text or "")


def employment_type_from_title(title: str) -> Optional[str]:
    t = strip_contract_work(title or "")
    if not t.strip():
        return None
    if _TITLE_C2H.search(t):
        return "contract_to_hire"
    if _TITLE_INTERN.search(t) and not re.search(r"\binternal\b", t, I) or re.search(r"\binterns?\b|\binternship\b", t, I):
        if re.search(r"\b(intern|interns|internship|co-?op)\b", t, I):
            return "internship"
    if _TITLE_FREELANCE.search(t):
        return "freelance"
    m = _TITLE_CONTRACT.search(t)
    if m:
        bad = _TITLE_CONTRACTOR_BAD.search(t)
        if not (bad and bad.start() <= m.start() <= bad.end()):
            return "contract"
    if _TITLE_1099.search(t):
        return "contract"
    if _TITLE_TEMP.search(t) and not re.search(r"\btemp(erature|late|o)\b", t, I):
        return "temporary"
    if _TITLE_PART.search(t):
        return "part_time"
    if _TITLE_FULL.search(t):
        return "full_time"
    return None


_ROLE = r"(?:role|position|assignment|opportunity|engagement|job|opening|gig|project|basis|work|hire|placement|requirement|consultant|resource)"
_NUMWORD = (r"(?:\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
            r"eighteen|twenty[- ]four|thirty[- ]six)")

_DESC_C2H = re.compile(
    r"\b(contract[- ]to[- ](hire|perm(anent)?)|c2h|temp[- ]to[- ](hire|perm(anent)?)|"
    r"contract with (a |the )?(possibility|potential|option) (of|for|to) (conversion|convert|extension and conversion|hire|full[- ]time)|"
    r"(possibility|potential|option) (of|for) (conversion|converting) to (full[- ]time|fte|permanent|perm)|"
    r"right[- ]to[- ]hire)\b", I)
_DESC_CONTRACT = [
    re.compile(r"\b" + _NUMWORD + r"\s*\+?\s*[- ]?\s*(?:to\s*\d+\s*)?(month|mo|week|wk|year|yr)s?\+?\s*(long\s*)?(w-?2\s*|1099\s*|c2c\s*)?contract(?!s)(?:or)?\b", I),
    re.compile(r"\bcontract(?:ual)?\s+" + _ROLE + r"\b", I),
    re.compile(r"\b(long|short|mid)[- ]term\s+contract\b", I),
    re.compile(r"\bon\s+an?\s+(\w+\s+)?contract(ual|or)?\s+basis\b", I),
    re.compile(r"\b(employment|job|position|work|engagement|role)\s*type\s*[:\-]\s*contract(?!s)(?:or)?\b(?![- ]to[- ]hire)", I),
    re.compile(r"\b(w-?2|1099|c2c|corp[- ]?to[- ]?corp)\s+(contract|contractor|only|" + _ROLE + r")\b", I),
    re.compile(r"\bcontract\s*(duration|length|term|period)\s*[:\-]", I),
    re.compile(r"\b(duration|assignment length|length of (assignment|contract|engagement)|project length|term)\s*[:\-]\s*\d", I),
    re.compile(r"\b(this|the|a|is an?)\s+(\w+\s+){0,2}contract(?:or)?\s+(" + _ROLE + r"|for|with|through)\b", I),
    re.compile(r"\b(independent contractor|as a contractor|hired as (a )?contractors?|contract employee|contingent worker)\b", I),
    re.compile(r"\b(this is|is) an? (\w+[- ])?contract\b(?!s|or|ual| (manage|negotiat|review|administ|law|lifecycle))", I),
]
_DESC_TEMP = re.compile(
    r"\b(temporary|seasonal)\s+(" + _ROLE + r"|employee|employment|staff)\b|\bthis is an? temp(orary)?\b", I)
_DESC_FREELANCE = re.compile(
    r"\bfreelance(r)?\s+(" + _ROLE + r"|contract|writer|designer)?|\bon an? freelance basis\b|\bas an? freelancer\b", I)
_DESC_INTERN = re.compile(r"\b(this|our|the|summer|paid|fall|spring)\s+internship\b|\binternship (program|role|position)\b", I)
_DESC_PART = re.compile(r"\bpart[- ]time\s+(" + _ROLE + r"|employee|employment|schedule)\b|\bthis is an? part[- ]time\b", I)
_DESC_FULL = re.compile(
    r"\b(this is an?|is an?)\s+(\w+[- ])?full[- ]time\b|\bfull[- ]time\s*,?\s*(permanent|salaried|exempt|w-?2 employee|employee|" + _ROLE + r")\b|"
    r"\b(employment|job|position)\s*type\s*[:\-]\s*full[- ]time\b", I)
_DESC_TYPE_FIELD = re.compile(r"\b(employment|job|position)\s*type\s*[:\-]\s*([A-Za-z][A-Za-z \-/()]{2,40})", I)

# Phrases that mention "contract(or)" without describing the job's terms.
_CONTRACT_NOISE = re.compile(
    r"\b(federal|government|defense|dod|vendor|customer|client|sales|supplier|commercial|prime|sub)[- ]?contract(or|ors|s|ing)?\b|"
    r"\bcontracts?\s+(negotiation|negotiations|management|review|administration|lifecycle)\b|"
    r"\bemployees?,?\s+(and|or)\s+contractors\b|\bcontractors?\s+(and|or)\s+(employees|vendors)\b", I)


# Legal / privacy / EEO boilerplate that mentions contractors without describing
# the job ("evaluate your application for employment or an independent contractor
# role, as applicable"). Sentences matching this are dropped before text detection.
_BOILERPLATE = re.compile(
    r"\bemployment or (?:an? )?(?:independent )?contract(?:or|ual)?\b|"
    r"\b(?:employees?|staff|workers?|personnel)\s*(?:,\s*(?:\w+\s+){0,3})?(?:and|or|&|/)\s*(?:independent\s+|external\s+)?contractors?\b|"
    r"\bcontractors?\s*(?:and|or|&|/)\s*(?:\w+\s+)?employees?\b|"
    r"\b(?:as|whether as|whether|either)\s+an?\s+employee\s+or\s+(?:an?\s+)?(?:independent\s+)?contractor\b|"
    r"\bindependent contractors?\s+(?:are|is|will be)\s+not\s+eligible\b|"
    r"\bnot eligible\b[^.]{0,60}\bcontractors?\b|"
    r"\b(?:equal (?:employment )?opportunity|eeo(?:c)?\b|affirmative action|privacy (?:notice|policy|statement)|"
    r"applicant privacy|personal (?:data|information)|reasonable accommodations?|e-?verify|"
    r"without regard to|protected veteran|sexual orientation|gender identity|pay transparency|"
    r"fair chance|arrest (?:and|or) conviction|background check)", I)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?;])\s+|\s*\n\s*|\s+(?=•)")


def strip_boilerplate(text: str) -> str:
    """Drop legal / privacy / EEO sentences (they mention contractors generically)."""
    if not text or not _BOILERPLATE.search(text):
        return text or ""
    return " ".join(p for p in _SENTENCE_SPLIT.split(text) if p and not _BOILERPLATE.search(p))


def employment_type_from_text(text: str) -> Optional[str]:
    if not text:
        return None
    text = strip_contract_work(strip_boilerplate(text))
    if not text.strip():
        return None
    m = _DESC_TYPE_FIELD.search(text)
    if m:
        mapped = map_employment_type_raw(m.group(2).split("  ")[0])
        if mapped:
            return mapped
    for m in _DESC_C2H.finditer(text):
        if not _negated(text, m.start()):
            return "contract_to_hire"
    if _DESC_INTERN.search(text):
        intern = True
    else:
        intern = False
    for m in _DESC_FREELANCE.finditer(text):
        if m.group(0).strip().lower() not in ("freelance", "freelancer") and not _negated(text, m.start()):
            return "freelance"
    for rx in _DESC_CONTRACT:
        for m in rx.finditer(text):
            span = text[max(0, m.start() - 25):m.end() + 5]
            if _negated(text, m.start()) or (_CONTRACT_NOISE.search(span) and not re.search(r"\b(w-?2|1099|c2c|duration|month|week|year)\b", m.group(0), I)):
                continue
            return "contract"
    for m in _DESC_TEMP.finditer(text):
        if not _negated(text, m.start()):
            return "temporary"
    if intern:
        return "internship"
    for m in _DESC_PART.finditer(text):
        if not _negated(text, m.start()):
            return "part_time"
    for m in _DESC_FULL.finditer(text):
        if not _negated(text, m.start()):
            return "full_time"
    return None


# ------------------------------------------------------------------ tax terms

_W2 = re.compile(r"(?<!form )\bw-?2\b(?!\s*(forms?|reporting|processing|filings?|preparation|statements?)\b)", I)
_C2C = re.compile(r"\b(c2c|corp[- ]?(to|2)[- ]?corp|corp-corp)\b", I)
_1099 = re.compile(r"(?<!form )\b1099\b(?![- ]?(misc|nec|int|div|k|b|r|s)\b)(?!\s*(forms?|reporting|filings?|processing|compliance|preparation|tax)\b)", I)
_NO_C2C = re.compile(
    r"\b(no|not open to|not accepting|cannot (do|accept|work with|consider)|can't (do|accept)|unable to (do|accept|work with|consider))\s+"
    r"(c2c|corp[- ]?(to|2)[- ]?corp)\b|"
    r"\b(c2c|corp[- ]?(to|2)[- ]?corp)\s*(is\s*|are\s*)?(not\s+(allowed|accepted|available|possible|considered|an option|supported|entertained)|n/?a)\b|"
    r"\bw-?2\s*(only|basis only)\b|\bonly\s+(on\s+)?w-?2\b|\bno\s+third[- ]part(y|ies)\b", I)
_W2_ONLY = re.compile(r"\bw-?2\s*(only|basis only)\b|\bonly\s+(on\s+)?w-?2\b", I)


def tax_terms_from_text(text: str) -> list[str]:
    found: list[str] = []
    if not text:
        return found
    for code, rx in (("w2", _W2), ("c2c", _C2C), ("1099", _1099)):
        for m in rx.finditer(text):
            before = text[max(0, m.start() - 20):m.start()]
            if re.search(r"\b(no|not|non|cannot|can't|unable to \w+)\s*$", before, I):
                continue
            after = text[m.end():m.end() + 30]
            if re.match(r"\s*(is\s*|are\s*)?(not\s+(allowed|accepted|available|possible|considered|an option|supported)|n/?a)\b", after, I):
                continue
            found.append(code)
            break
    if _W2_ONLY.search(text):
        found = [t for t in found if t == "w2"] or ["w2"]
    return [t for t in TAX_TERMS if t in found]


# ------------------------------------------------------------------ visa terms

_H1B = r"h-?1-?b(?:\s*visa)?s?"
_VISA_RULES: list[tuple[str, re.Pattern]] = [
    ("usc_only", re.compile(
        r"\b(usc|us citizens?|u\.s\.? citizens?|united states citizens?|american citizens?)(hip)?\s*(only|required|is required|are required)\b|"
        r"\bonly\s+(usc|us citizens|u\.s\.? citizens|united states citizens)\b|"
        r"\bmust\s+be\s+(an?\s+)?(us|u\.s\.?|united states|american)\s+citizens?\b|"
        r"\b(us|u\.s\.?|united states) citizenship (is )?(required|mandatory)\b|\brequires? (us|u\.s\.?) citizenship\b", I)),
    ("usc_gc_only", re.compile(
        r"\b(usc|us citizens?|u\.s\.? citizens?|citizens?)\s*(/|,|or|and|&|\+)\s*(gc|green ?card|permanent residents?|lawful permanent residents?)(\s*holders?)?\b"
        r"(?!\s*(/|,|or|and|&|\+)\s*(gc[- ]?ead|ead|h-?1-?b|h4|l2|tn|opt|cpt))|"
        r"\b(gc|green ?card)\s*holders?\s*(only|required)\b|\bonly\s+(usc|us citizens?)\s*(and|or|/|&)\s*(gc|green ?card)", I)),
    ("gc_ead_ok", re.compile(r"\b(gc[\s/-]*ead|green ?card[\s/-]*ead|h-?4[\s/-]*ead|l-?2[\s/-]*ead|ead)\b(?!\s*(not|is not|are not)\b)", I)),
    ("h1b_transfer", re.compile(r"\b" + _H1B + r"\s*(visa\s*)?transfers?\b|\btransfer\s+(of\s+)?(an?\s+)?(existing\s+)?" + _H1B + r"\b", I)),
    ("h1b_ok", re.compile(
        r"\b" + _H1B + r"\s*(candidates\s*|holders\s*|applicants\s*)?(are\s*|is\s*)?(ok|okay|welcome|fine|accepted|considered|eligible|can apply|allowed)\b|"
        r"\b(gc|usc|ead|citizens?|green ?card)\s*(/|,|or|and|&)\s*([\w-]+\s*(/|,|or|and|&)\s*){0,4}" + _H1B + r"\b(?!\s*transfer)", I)),
    ("no_c2c", _NO_C2C),
    ("no_sponsorship", re.compile(
        r"\b(no|not|without|unable to|cannot|can ?not|can't|won't|will not|do not|does not|don't|doesn't|are not able to|is not able to|not able to|unable to provide|not eligible for|not offering|not provide|not providing)\b[\w\s,/()-]{0,40}?\b(sponsor|sponsorship|sponsoring|sponsored)\b|"
        r"\b(visa\s+)?sponsorship\s*(is\s*|will\s*)?(not|never|no longer)\s*(be\s*)?(available|offered|provided|possible|supported|an option|considered)\b|"
        r"\b(visa\s+)?sponsorship\s*[:\-]\s*(no|none|not available|n/?a)\b|"
        r"\bmust\s+(be\s+)?(legally\s+)?(authorized|eligible)\s+to\s+work\s+in\s+the\s+(us|u\.s\.?|united states)\s+without\b", I)),
    ("sponsorship_available", re.compile(
        r"\b(will|can|may|we|able to|happy to|open to|willing to)\s+(consider\s+)?sponsor(ing)?\b(?!ship)|"
        r"\b(visa\s+|h-?1-?b\s+)?sponsorship\s*(is\s*|will be\s*)?(available|offered|provided|possible|supported)\b|"
        r"\b(visa\s+)?sponsorship\s*[:\-]\s*(yes|available)\b|\bsponsorship (is )?an option\b|\bprovides? (visa |h-?1-?b )?sponsorship\b", I)),
    ("security_clearance", re.compile(
        r"\b(security\s+)?clearance\s*(is\s*)?(required|needed|mandatory)\b|"
        r"\b(active|current|existing|valid|interim)\b[\w\s/-]{0,30}\bclearance\b|"
        r"\bts\s*/\s*sci\b|\btop\s*secret(\s*/\s*sci)?(\s+security)?\s+clearance\b|\btop secret/sci\b|"
        r"\b(secret|public trust|q|dod|doe|ts)\s+(security\s+)?clearance\b|"
        r"\b(obtain|hold|possess|maintain|eligible for|eligibility for|able to obtain)\b[\w\s,-]{0,40}\bclearance\b|"
        r"\bpolygraph\b", I)),
]
_CLEARANCE_NEG = re.compile(r"\b(no|not|without|does not require|doesn't require)\b[\w\s]{0,20}\bclearance\b|\bclearance\s+(is\s+)?not\s+required\b", I)
_H1B_NEG_BEFORE = re.compile(r"\b(no|not|cannot|can't|can ?not|unable|won't|will not|don't|do not|doesn't|does not|without|except)\b[\w\s,/-]{0,40}$", I)


def visa_terms_from_text(text: str) -> list[str]:
    found: set[str] = set()
    if not text:
        return []
    for code, rx in _VISA_RULES:
        for m in rx.finditer(text):
            if code in ("usc_only", "usc_gc_only", "gc_ead_ok", "sponsorship_available") and _negated(text, m.start(), 20):
                continue
            if code in ("h1b_ok", "h1b_transfer"):
                if _H1B_NEG_BEFORE.search(text[max(0, m.start() - 45):m.start()]):
                    continue
                if re.match(r"[\w\s]{0,15}\b(not|no)\b", text[m.end():m.end() + 25], I):
                    continue
            if code == "sponsorship_available" and _H1B_NEG_BEFORE.search(text[max(0, m.start() - 25):m.start()]):
                continue
            if code == "security_clearance":
                ctx = text[max(0, m.start() - 30):m.end() + 20]
                if _CLEARANCE_NEG.search(ctx):
                    continue
            found.add(code)
            break
    # "No C2C" / "W2 only" ... also "No sponsorship" beats a generic "can sponsor" mention.
    if "no_sponsorship" in found and "sponsorship_available" in found:
        found.discard("sponsorship_available")
    if "usc_only" in found:
        found.discard("usc_gc_only")
    return [v for v in VISA_TERMS if v in found]


# --------------------------------------------------------------------------- pay

_AMOUNT = r"(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?\s*([kK])?"
_CUR = r"(?:US\$|\$|USD\s*)"
_PAY_RE = re.compile(
    _CUR + r"\s*" + _AMOUNT +
    r"(?:\s*(?:USD)?\s*(?:/\s*(?:hr|hour|h))?\s*(?:-|–|—|to)\s*(?:" + _CUR + r")?\s*" + _AMOUNT + r")?", I)
_PAY_SUFFIX_RE = re.compile(
    r"\b" + _AMOUNT + r"(?:\s*(?:-|–|—|to)\s*" + _AMOUNT + r")?\s*(?:USD|dollars)\b", I)
_PERIOD_RULES = [
    ("hour", re.compile(r"^\s*(usd\s*)?(/|per|an|a|p/?)\s*(hr|hour|h)\b|^\s*(usd\s*)?(hourly|/hr|ph\b|p/h\b|hr\b)", I)),
    ("day", re.compile(r"^\s*(usd\s*)?(/|per|a)\s*(day|diem)\b|^\s*(usd\s*)?daily\b", I)),
    ("week", re.compile(r"^\s*(usd\s*)?(/|per|a)\s*(week|wk)\b|^\s*(usd\s*)?weekly\b", I)),
    ("month", re.compile(r"^\s*(usd\s*)?(/|per|a)\s*(month|mo)\b|^\s*(usd\s*)?monthly\b", I)),
    ("year", re.compile(r"^\s*(usd\s*)?(/|per|a|an)\s*(year|yr|annum)\b|^\s*(usd\s*)?(annually|annual|yearly|/yr|pa\b|p\.a\.)", I)),
]
_PAY_NOISE_AFTER = re.compile(r"^\s*(\+\s*)?(million|billion|m\b|b\b|bn\b|in (funding|revenue|sales|annual)|bonus|sign[- ]on|signing|stipend|funding|raised|revenue|equity|in stock|401|reimburse|per (employee|referral|month for|year for)|towards|learning|wellness|allowance|referral|credit)", I)
_PAY_NOISE_BEFORE = re.compile(r"(bonus|stipend|funding|raised|revenue|valuation|allowance|reimburse\w*|budget|up to|credit|referral|401\(?k\)?|match)\W{0,3}(of\s+)?(up to\s+)?$", I)
_PAY_CONTEXT_BEFORE = re.compile(r"(pay|rate|salary|compensation|comp|wage|range|base|hourly|ote|earn|paying|pays|bill|budget)\b[^$.\n]{0,40}$", I)


def _num(whole: Optional[str], frac: Optional[str], k: Optional[str]) -> Optional[float]:
    if not whole:
        return None
    v = float(whole.replace(",", "") + ("." + frac if frac else ""))
    if k:
        v *= 1000
    return v


def _period_after(text: str, pos: int) -> Optional[str]:
    tail = text[pos:pos + 25]
    for period, rx in _PERIOD_RULES:
        if rx.search(tail):
            return period
    return None


def _valid_pay(lo: float, hi: float, period: str) -> bool:
    b = _PAY_BOUNDS[period]
    return b[0] <= lo <= b[1] and b[0] <= hi <= b[1] and hi <= lo * 4


def parse_pay(text: str) -> Optional[tuple[float, Optional[float], str]]:
    """(min, max_or_None, period) from free text, or None."""
    if not text:
        return None
    labeled: list[tuple[float, Optional[float], str]] = []
    inferred: list[tuple[float, Optional[float], str]] = []
    matches = [(m, 1) for m in _PAY_RE.finditer(text)] + [(m, 2) for m in _PAY_SUFFIX_RE.finditer(text)]
    matches.sort(key=lambda x: x[0].start())
    for m, kind in matches:
        g = m.groups()
        lo = _num(g[0], g[1], g[2])
        hi = _num(g[3], g[4], g[5]) if g[3] else None
        if lo is None:
            continue
        # "$120-150k": the k applies to both ends
        if hi is not None and g[5] and not g[2] and lo < 1000 <= hi:
            lo *= 1000
        if _PAY_NOISE_AFTER.search(text[m.end():m.end() + 25]):
            continue
        before = text[max(0, m.start() - 60):m.start()]
        if _PAY_NOISE_BEFORE.search(before):
            continue
        # A trailing "/hr" inside the range pattern ("$60/hr - $75/hr")
        inner_hour = re.search(r"/\s*(hr|hour|h)\b", m.group(0), I)
        period = _period_after(text, m.end()) or ("hour" if inner_hour else None)
        if period is None and hi is None and m.group(0).rstrip().lower().endswith(("k",)):
            period = "year"
        if period is None:
            # No unit: infer from magnitude, only in a pay context.
            ref = hi if hi is not None else lo
            ctx = bool(_PAY_CONTEXT_BEFORE.search(before))
            if ref >= 15000 and (hi is not None or ctx or g[2]):
                period = "year"
            elif ref <= 500 and ctx and re.search(r"\b(rate|hourly|bill)\b", before[-40:], I):
                period = "hour"
            else:
                continue
            target = inferred
        else:
            target = labeled
        if hi is not None and hi < lo:
            lo, hi = hi, lo
        if not _valid_pay(lo, hi if hi is not None else lo, period):
            continue
        target.append((lo, hi, period))
    if labeled:
        # Prefer an hourly/daily quote (contract rate) when both exist.
        for lo, hi, p in labeled:
            if p in ("hour", "day"):
                return lo, hi, p
        return labeled[0]
    return inferred[0] if inferred else None


# ---------------------------------------------------------------------- duration

_WORDNUM = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
            "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "eighteen": 18, "twenty four": 24,
            "twenty-four": 24, "thirty six": 36, "thirty-six": 36, "a": 1, "an": 1}
_N = r"(\d{1,2}|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|eighteen|twenty[- ]four|thirty[- ]six)"
_UNIT = r"(months?|mos?\.?|mths?|years?|yrs?|weeks?|wks?)"
_DUR_RANGE = re.compile(r"\b" + _N + r"\s*\+?\s*(?:-|–|—|to)\s*" + _N + r"\s*\+?\s*[- ]?" + _UNIT + r"(?![a-z])", I)
_DUR_SINGLE = re.compile(r"\b(" + _N[1:-1] + r"|a|an)\s*\+?\s*[- ]?" + _UNIT + r"\+?(?![a-z])", I)
_DUR_CONTEXT = re.compile(r"\b(contract|duration|assignment|engagement|project|term|length|extension|initial|temp|temporary|c2h|ctc|w-?2|1099|c2c|possible|likely)\b", I)
_DUR_FIELD = re.compile(r"\b(duration|contract (length|duration|term)|length of (assignment|contract|engagement)|assignment (length|duration)|project (length|duration)|term)\s*[:\-]\s*", I)
_DUR_EXPERIENCE = re.compile(r"^\s*\+?\s*(of\s+)?(\w+\s+)?(experience|exp\b|in\s+(the\s+)?(industry|role|field)|old|ago|of age|professional|hands[- ]on|working|relevant)", I)


def _to_int(tok: str) -> Optional[int]:
    tok = tok.lower().replace("-", " ")
    if tok.isdigit():
        return int(tok)
    return _WORDNUM.get(tok) or _WORDNUM.get(tok.replace(" ", "-"))


def _unit_months(n: int, unit: str) -> int:
    u = unit.lower()
    if u.startswith(("y",)):
        return n * 12
    if u.startswith("w"):
        return max(1, math.ceil(n / 4.345))
    return n


def parse_duration_months(text: str, contract_known: bool = False) -> Optional[int]:
    """Minimum contract length in months ("6-12 months" -> 6, "12+ months" -> 12).

    Without contract context nearby a bare "6 months" is ignored, unless the job
    is already known to be a contract (``contract_known``)."""
    if not text:
        return None
    best: Optional[tuple[int, int]] = None  # (priority, months); lower priority wins
    for rx, is_range in ((_DUR_RANGE, True), (_DUR_SINGLE, False)):
        for m in rx.finditer(text):
            if _DUR_EXPERIENCE.search(text[m.end():m.end() + 40]):
                continue
            before = text[max(0, m.start() - 45):m.start()]
            after = text[m.end():m.end() + 30]
            if re.search(r"\b(experience|within|first|after|every|each|per|ago|at least)\W*$", before[-15:], I):
                continue
            if not is_range and re.search(r"\d\s*\+?\s*(-|–|—|to)\s*$", before[-6:], I):
                continue  # the upper end of a range ("6-9 months") - the range match decides
            field = bool(_DUR_FIELD.search(before[-30:]))
            ctx = field or _DUR_CONTEXT.search(before[-35:] + " " + after[:25])
            if not ctx and not contract_known:
                continue
            n = _to_int(m.group(1))
            unit = m.group(3) if is_range else m.group(2)
            if n is None or not unit:
                continue
            months = _unit_months(n, unit)
            if not (1 <= months <= 60):
                continue
            # "5+ years in Python" is experience, not term: years only count
            # next to explicit contract wording ("Duration: 1 year",
            # "2 year contract", "1-year assignment"), never on context alone.
            if unit.lower().startswith("y") and not field and not re.match(
                    r"\s*(long\s*)?(w-?2\s*|c2c\s*|1099\s*)?(contract|assignment|engagement|term|project|extension)\b", after, I) \
                    and not re.search(r"\b(contract|assignment|engagement|duration|term)\s*(length|duration|of|for|is|:)?\s*(up\s+to\s+|approximately\s+|about\s+)?$", before[-30:], I):
                continue
            if field or re.match(r"\s*(long\s*)?(w-?2\s*|c2c\s*)?(contract|assignment|engagement|contract[- ]to[- ]hire)\b", after, I):
                prio = 0  # "Duration: 6 months", "18 month contract"
            elif re.search(r"\b(contract|assignment|engagement|duration)\b", before[-35:] + after[:25], I):
                prio = 1
            else:
                prio = 2
            if best is None or prio < best[0]:
                best = (prio, months)
    return best[1] if best else None


# ---------------------------------------------------------------------- location
# Shared with the full-time pipeline (neither pipeline imports the other for this).
from services.job_location import is_us_location, job_countries  # noqa: E402,F401


# ------------------------------------------------------------------------ classify

def _f(value: Any) -> Optional[float]:
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and v > 0 else None


def _norm_period(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    v = str(value).strip().lower()
    table = {"hour": "hour", "hourly": "hour", "hr": "hour", "h": "hour", "per_hour": "hour",
             "day": "day", "daily": "day", "week": "week", "weekly": "week", "wk": "week",
             "month": "month", "monthly": "month", "mo": "month", "year": "year", "yearly": "year",
             "annual": "year", "annually": "year", "yr": "year", "salary": "year", "per_year": "year"}
    return table.get(v) or table.get(v.replace("per ", "").replace("per_", ""))


def _employment_type(title: str, text: str, raw: dict, raw_type_text: str, extra_text: str) -> Optional[str]:
    """ATS field > title > description (an explicit contract title beats an ATS "Full-time" default)."""
    ats_type = map_employment_type_raw(raw.get("employment_type_raw")) or map_employment_type_raw(raw.get("employment_type"))
    title_type = employment_type_from_title(title)
    if ats_type and not (ats_type in ("full_time", "part_time") and title_type in CONTRACT_TYPES):
        if ats_type == "contract" and (title_type == "contract_to_hire" or employment_type_from_text(text) == "contract_to_hire"):
            return "contract_to_hire"
        return ats_type
    employment_type = title_type or employment_type_from_text(text)
    if employment_type in (None, "full_time", "part_time") and (raw_type_text.strip() or extra_text):
        # An explicit type field in the scraped extra/raw text (staffing boards)
        et = employment_type_from_text(" ".join((raw_type_text, extra_text)))
        if et and et != "full_time" and (employment_type is None or et in CONTRACT_TYPES):
            employment_type = et
    return employment_type


_C2C_OR_1099 = re.compile(r"\b(c2c|corp[- ]?(to|2)[- ]?corp)\b", I)


def classify(
    title: Optional[str],
    description: Optional[str] = None,
    location: Optional[str] = None,
    raw: Optional[dict] = None,
) -> dict:
    """Classify one job. Returns the job columns (never raises on odd input)."""
    raw = dict(raw or {})
    extra = raw.get("extra") or {}
    title = (title or "").strip()
    text = to_text(description)
    extra_text = " ".join(str(v) for v in extra.values() if isinstance(v, (str, int, float))) if isinstance(extra, dict) else ""
    raw_type_text = " ".join(str(raw.get(k) or "") for k in ("employment_type_raw", "employment_type"))
    full = " \n ".join(p for p in (title, raw_type_text, extra_text, text) if p)

    employment_type = _employment_type(title, text, raw, raw_type_text, extra_text)

    tax_terms = tax_terms_from_text(full)
    visa_terms = visa_terms_from_text(full)
    if "no_c2c" in visa_terms and "c2c" in tax_terms:
        tax_terms = [t for t in tax_terms if t != "c2c"]
    if employment_type is None and "c2c" in tax_terms:
        employment_type = "contract"
    if employment_type is None and "1099" in tax_terms:
        employment_type = "freelance"

    # Pay: structured first, then text, then yearly salary columns.
    pay_min, pay_max = _f(raw.get("pay_rate_min")), _f(raw.get("pay_rate_max"))
    pay_period = _norm_period(raw.get("pay_period"))
    if (pay_min or pay_max) and pay_period:
        lo, hi = pay_min or pay_max, pay_max or pay_min
        if hi < lo:
            lo, hi = hi, lo
        if not _valid_pay(lo, hi, pay_period):
            pay_min = pay_max = pay_period = None
        else:
            pay_min, pay_max = lo, (hi if hi != lo or pay_max else None)
    else:
        pay_min = pay_max = pay_period = None
    if pay_period is None:
        parsed = parse_pay(" \n ".join(p for p in (title, extra_text, text) if p))
        if parsed:
            pay_min, pay_max, pay_period = parsed
    if pay_period is None:
        smin, smax = _f(raw.get("salary_min")), _f(raw.get("salary_max"))
        if smin or smax:
            lo, hi = smin or smax, smax or smin
            if hi < lo:
                lo, hi = hi, lo
            if _valid_pay(lo, hi, "year"):
                pay_min, pay_max, pay_period = lo, (hi if hi != lo else None), "year"
    if pay_min is not None:
        pay_min = round(pay_min, 2)
    if pay_max is not None:
        pay_max = round(pay_max, 2)

    # Contract length (only meaningful off the permanent track)
    duration = None
    if employment_type not in ("full_time", "part_time"):
        duration = parse_duration_months(" \n ".join(p for p in (title, extra_text, text) if p),
                                         contract_known=employment_type in CONTRACT_TYPES)
        if duration is not None and employment_type is None:
            employment_type = "contract"

    return {
        "employment_type": employment_type,
        "tax_terms": tax_terms or None,
        "pay_rate_min": pay_min,
        "pay_rate_max": pay_max,
        "pay_period": pay_period,
        "contract_duration_months": duration,
        "visa_terms": visa_terms or None,
        "countries": job_countries(location, title),
    }


CLASSIFIED_FIELDS = (
    "employment_type", "tax_terms", "pay_rate_min", "pay_rate_max", "pay_period",
    "contract_duration_months", "visa_terms", "countries",
)


def raw_fields_from_scraped(scraped_job: Any) -> dict:
    """Structured fields off a ScrapedJob (tolerates older objects without them)."""
    g = lambda k: getattr(scraped_job, k, None)  # noqa: E731
    return {
        "employment_type_raw": g("employment_type_raw"),
        "employment_type": g("employment_type"),
        "pay_rate_min": g("pay_rate_min"),
        "pay_rate_max": g("pay_rate_max"),
        "pay_period": g("pay_period"),
        "salary_min": g("salary_min"),
        "salary_max": g("salary_max"),
        "extra": g("extra") or {},
    }


def classify_fields(title, description, location, raw: Optional[dict] = None) -> dict:
    """classify() + classified_at, never raising (a classifier bug must not block saving)."""
    try:
        out = classify(title, description, location, raw)
    except Exception:  # pragma: no cover - defensive
        out = {k: None for k in CLASSIFIED_FIELDS}
    out["classified_at"] = datetime.utcnow()
    return out




def detect_employment_type(title: Optional[str], description: Optional[str] = None,
                           raw: Optional[dict] = None) -> Optional[str]:
    """Employment type only (cheap; used by the full-time save path to route contracts out)."""
    try:
        raw = dict(raw or {})
        extra = raw.get("extra") or {}
        extra_text = " ".join(str(v) for v in extra.values() if isinstance(v, (str, int, float))) if isinstance(extra, dict) else ""
        raw_type_text = " ".join(str(raw.get(k) or "") for k in ("employment_type_raw", "employment_type"))
        text = strip_boilerplate(to_text(description))
        et = _employment_type((title or "").strip(), text, raw, raw_type_text, extra_text)
        if et is None and _C2C_OR_1099.search(text):
            terms = tax_terms_from_text(text)
            if "c2c" in terms:
                et = "contract"
        return et
    except Exception:  # never block a save on a classifier bug
        return None


# Types that always go to contract_jobs; "temporary" only with contract evidence.
ROUTED_TYPES = ("contract", "contract_to_hire", "freelance")
_CONTRACT_WORD = re.compile(r"\b(contract(or)?|contract[- ]to[- ]hire|c2h|corp[- ]?to[- ]?corp)\b", I)


def _has_contract_wording(text: str) -> bool:
    text = strip_contract_work(strip_boilerplate(text))
    for m in _CONTRACT_WORD.finditer(text):
        span = text[max(0, m.start() - 25):m.end() + 25]
        if _negated(text, m.start()) or _CONTRACT_NOISE.search(span):
            continue
        return True
    return False


_TITLE_TEMP_WORD = re.compile(r"\btemp(orary)?\b(?!erature|late)", I)
_RAW_CONTRACT_TERMS = re.compile(r"\b(contract|contractor|contractual|c2c|corp[- ]?to[- ]?corp|1099|w-?2|c2h)\b", I)


def _raw_type_value(raw: dict) -> Optional[str]:
    for k in ("employment_type_raw", "employment_type"):
        v = raw.get(k)
        if isinstance(v, (list, tuple)):
            v = " ".join(str(x) for x in v if x)
        if v and str(v).strip():
            return str(v)
    return None


def title_contract_type(title: Optional[str]) -> Optional[str]:
    """
    Employment type from explicit title markers only: Contract, Contractor, C2H,
    Contract-to-Hire, Temp, Temporary, Freelance, 1099. "Seasonal" alone is not
    a marker (direct-hire retail).
    """
    et = employment_type_from_title(title or "")
    if et == "temporary" and not _TITLE_TEMP_WORD.search(title or ""):
        return None
    return et if et in CONTRACT_TYPES else None


def company_board_routing(title: Optional[str], raw: Optional[dict] = None,
                          description: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """
    Routing for anything that is not a staffing scraper (company boards,
    aggregators): contracts ONLY when

    (a) the ATS's structured employment field says contract / contract-to-hire /
        freelance, or temporary with contract terms in the field itself
        ("Temporary (Contract)", "Temp - W2"), or
    (b) the title carries an explicit marker (Contract, Contractor, C2H,
        Contract-to-Hire, Temp, Temporary, Freelance, 1099).

    The description is never used to route (privacy / EEO boilerplate such as
    "employment or an independent contractor role" misrouted full-time roles);
    it only labels non-routed rows (full_time / part_time / internship).
    """
    raw = dict(raw or {})
    raw_value = _raw_type_value(raw)
    ats = map_employment_type_raw(raw_value) if raw_value else None
    t_type = title_contract_type(title)
    if t_type:
        if t_type == "contract" and ats == "contract_to_hire":
            return True, "contract_to_hire"
        return True, t_type
    if ats in ("contract", "contract_to_hire", "freelance"):
        return True, ats
    if ats == "temporary" and raw_value and _RAW_CONTRACT_TERMS.search(raw_value):
        return True, "temporary"
    # Not routed: best non-contract label for the jobs row.
    if ats:
        return False, ats
    et = employment_type_from_title(title or "")
    if et:
        return False, et
    try:
        text_type = employment_type_from_text(to_text(description)) if description else None
    except Exception:
        text_type = None
    return False, text_type if text_type in ("full_time", "part_time", "internship") else None


def contract_routing(title: Optional[str], description: Optional[str] = None, raw: Optional[dict] = None,
                     staffing: bool = False) -> tuple[bool, Optional[str]]:
    """
    The single rule deciding whether a posting belongs in contract_jobs.
    Returns (route_to_contracts, employment_type).

    Non-staffing sources (company boards, aggregators): company_board_routing()
    - structured ATS field or explicit title marker only, never description text.

    Staffing sources: contract / contract_to_hire / freelance -> contracts;
    temporary -> contracts (a staffing source is contract evidence).
    """
    if not staffing:
        try:
            return company_board_routing(title, raw, description)
        except Exception:  # never block a save on a classifier bug
            return False, None
    et = detect_employment_type(title, description, raw)
    if et in ROUTED_TYPES:
        return True, et
    if et == "temporary":
        if staffing:
            return True, et
        try:
            full = f"{title or ''} \n {to_text(description)}"
            if tax_terms_from_text(full):
                return True, et
            pay = parse_pay(full)
            if pay and pay[2] in ("hour", "day") and _has_contract_wording(full):
                return True, et
        except Exception:
            pass
    return False, et


def is_contract_type(employment_type: Optional[str]) -> bool:
    return employment_type in CONTRACT_TYPES
