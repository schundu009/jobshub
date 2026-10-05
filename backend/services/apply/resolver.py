"""
AnswerResolver: fill a normalized form schema.

Rules
- Factual categories (identity, links, work_auth, sponsorship, relocation,
  salary, start_date, eeo) come ONLY from the saved profile.
- EEO: the saved value only when the customer opted in; otherwise the form's
  "decline to self-identify" option; otherwise needs_user (if required).
- Attestations (arbitration, AI policy, privacy/recording consent, background
  checks, ...) are never answered automatically: required -> needs_user.
- Custom questions: answer bank (by normalized label), then an AI draft for
  required free-text questions (source ai_draft, confirmed=False).
- Anything required and still unresolved -> needs_user.

Answer entry: {value, source, confirmed, needs_user}
  source: profile | bank | ai_draft | user | None
"""
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

DECLINE_RE = re.compile(
    r"decline|don.?t wish|do not wish|prefer not|not to (answer|say|disclose)|choose not|rather not|not wish to", re.I)

MAX_RESUME_CHARS = 12000
MAX_JD_CHARS = 8000


def normalize_question_key(label: str) -> str:
    text = (label or "").lower()
    text = re.sub(r"^\s*\(optional\)\s*", "", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:500]


def _yes_no(value: Optional[bool]) -> Optional[str]:
    if value is None:
        return None
    return "Yes" if value else "No"


def match_option(options: List[str], value: Any) -> Optional[str]:
    """Best option label for a value (exact, then prefix/containment, then yes/no)."""
    if value is None or not options:
        return None
    target = str(value).strip().lower()
    if not target:
        return None
    for opt in options:
        if opt.strip().lower() == target:
            return opt
    if target in ("yes", "no"):
        for opt in options:
            if opt.strip().lower().startswith(target):
                return opt
        return None
    for opt in options:
        low = opt.strip().lower()
        if low.startswith(target) or target.startswith(low):
            return opt
    matches = [opt for opt in options if target in opt.lower()]
    if len(matches) == 1:
        return matches[0]
    return None


def decline_option(options: List[str]) -> Optional[str]:
    for opt in options or []:
        if DECLINE_RE.search(opt):
            return opt
    return None


@dataclass
class ProfileView:
    """Everything the resolver may read about the customer. No credentials."""
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    preferred_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    address_line1: Optional[str] = None
    postal_code: Optional[str] = None
    linkedin: Optional[str] = None
    github: Optional[str] = None
    portfolio: Optional[str] = None
    twitter: Optional[str] = None
    work_authorized_us: Optional[bool] = None
    requires_sponsorship: Optional[bool] = None
    willing_to_relocate: Optional[bool] = None
    earliest_start_date: Optional[str] = None
    salary_expectation: Optional[str] = None
    notice_period: Optional[str] = None
    eeo_opt_in: bool = False
    gender: Optional[str] = None
    race: Optional[str] = None
    veteran: Optional[str] = None
    disability: Optional[str] = None
    resume_filename: Optional[str] = None
    resume_text: Optional[str] = None
    bank: Dict[str, str] = field(default_factory=dict)  # question_key -> value

    @property
    def full_name(self) -> Optional[str]:
        name = " ".join(p for p in (self.first_name, self.last_name) if p)
        return name or None

    @property
    def location(self) -> Optional[str]:
        parts = [p for p in (self.city, self.state, self.country) if p]
        return ", ".join(parts) or None


@dataclass
class JobContext:
    title: str = ""
    company: str = ""
    description: str = ""


def _identity_value(label: str, qid: str, p: ProfileView) -> Optional[str]:
    low = label.lower()
    key = qid.lower()
    if "first name" in low or key == "first_name":
        return p.first_name
    if "last name" in low or key == "last_name":
        return p.last_name
    if "preferred name" in low:
        return p.preferred_name or p.first_name
    if "name" in low and "company" not in low:
        return p.full_name
    if "email" in low or "e-mail" in low:
        return p.email
    if "phone" in low or "mobile" in low:
        return p.phone
    if "zip" in low or "postal" in low:
        return p.postal_code
    if "address" in low:
        return p.address_line1
    if "city" in low:
        return p.city
    if "countr" in low:
        return p.country
    if "state" in low:
        return p.state
    if "location" in low or "located" in low or "based" in low or "reside" in low or key == "location":
        return p.location
    return None


def _links_value(label: str, p: ProfileView) -> Optional[str]:
    low = label.lower()
    if "linkedin" in low:
        return p.linkedin
    if "github" in low:
        return p.github
    if "twitter" in low:
        return p.twitter
    if "portfolio" in low or "website" in low or "personal site" in low or "blog" in low:
        return p.portfolio
    return None


def _eeo_profile_value(label: str, p: ProfileView) -> Optional[str]:
    low = label.lower()
    if "gender" in low or "transgender" in low:
        return p.gender
    if "race" in low or "ethnic" in low or "hispanic" in low or "latin" in low:
        return p.race
    if "veteran" in low:
        return p.veteran
    if "disabilit" in low:
        return p.disability
    return None


def _entry(value=None, source=None, confirmed=False, needs_user=False) -> Dict[str, Any]:
    return {"value": value, "source": source, "confirmed": bool(confirmed), "needs_user": bool(needs_user)}


def _blank_or_needed(q) -> Dict[str, Any]:
    return _entry(needs_user=bool(q.get("required")))


def _fit(q: Dict[str, Any], value: Any) -> Any:
    """Coerce a profile value into the question's shape; None when it does not fit."""
    if value is None or value == "":
        return None
    qtype = q.get("type")
    options = q.get("options") or []
    if qtype in ("select", "boolean") and options:
        return match_option(options, value)
    if qtype == "multiselect" and options:
        opt = match_option(options, value)
        return [opt] if opt else None
    if qtype == "boolean":
        if isinstance(value, bool):
            return value
        low = str(value).strip().lower()
        return True if low == "yes" else False if low == "no" else None
    if qtype == "file":
        return None
    return value


class AnswerResolver:
    def __init__(self, profile: ProfileView, job: JobContext,
                 ai_drafter: Optional[Callable[[List[Dict[str, Any]], ProfileView, JobContext], Dict[str, str]]] = None,
                 cover_letter_text: Optional[str] = None):
        self.p = profile
        self.job = job
        self.ai_drafter = ai_drafter if ai_drafter is not None else draft_with_ai
        self.cover_letter_text = cover_letter_text

    def resolve(self, questions: List[Dict[str, Any]],
                existing: Optional[Dict[str, Dict[str, Any]]] = None) -> Dict[str, Dict[str, Any]]:
        existing = existing or {}
        answers: Dict[str, Dict[str, Any]] = {}
        to_draft: List[Dict[str, Any]] = []

        for q in questions:
            qid = q["id"]
            prior = existing.get(qid)
            if prior and prior.get("source") == "user":
                answers[qid] = dict(prior)  # never overwrite the customer's own answer
                continue
            entry = self._resolve_one(q)
            if entry is None:  # custom free text awaiting an AI draft
                to_draft.append(q)
                answers[qid] = _entry(needs_user=bool(q.get("required")))
            else:
                answers[qid] = entry

        if to_draft:
            drafts: Dict[str, str] = {}
            try:
                drafts = self.ai_drafter(to_draft, self.p, self.job) or {}
            except Exception as e:
                logger.warning("AI draft failed: %s", e)
            for q in to_draft:
                text = (drafts.get(q["id"]) or "").strip()
                if text:
                    answers[q["id"]] = _entry(text, "ai_draft", confirmed=False, needs_user=False)
        return answers

    # ------------------------------------------------------------------ per category

    def _profile(self, q, value) -> Dict[str, Any]:
        fitted = _fit(q, value)
        if fitted is None:
            return _blank_or_needed(q)
        return _entry(fitted, "profile", confirmed=True)

    def _resolve_one(self, q: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        category = q.get("category") or "custom"
        label = q.get("label") or ""
        p = self.p

        if category == "resume":
            if q.get("type") == "file" and p.resume_filename:
                return _entry(p.resume_filename, "profile", confirmed=True)
            if q.get("type") in ("text", "textarea") and p.resume_text:
                return _entry(p.resume_text[:MAX_RESUME_CHARS], "profile", confirmed=True)
            return _blank_or_needed(q)

        if category == "cover_letter":
            if self.cover_letter_text and q.get("type") in ("text", "textarea", "file"):
                return _entry(self.cover_letter_text, "profile", confirmed=True)
            return _blank_or_needed(q)

        if category == "identity":
            return self._profile(q, _identity_value(label, q["id"], p))

        if category == "links":
            return self._profile(q, _links_value(label, p))

        if category == "work_auth":
            return self._profile(q, _yes_no(p.work_authorized_us))

        if category == "sponsorship":
            return self._profile(q, _yes_no(p.requires_sponsorship))

        if category == "relocation":
            return self._profile(q, _yes_no(p.willing_to_relocate))

        if category == "salary":
            return self._profile(q, p.salary_expectation)

        if category == "start_date":
            if "notice" in label.lower():
                return self._profile(q, p.notice_period)
            value = p.earliest_start_date
            if value and q.get("type") in ("text", "textarea") and p.notice_period:
                value = f"{value} ({p.notice_period} notice)"
            return self._profile(q, value or p.notice_period)

        if category == "eeo":
            options = q.get("options") or []
            if p.eeo_opt_in:
                fitted = _fit(q, _eeo_profile_value(label, p))
                if fitted is not None:
                    return _entry(fitted, "profile", confirmed=True)
            declined = decline_option(options)
            if declined:
                return _entry([declined] if q.get("type") == "multiselect" else declined, "profile", confirmed=True)
            return _blank_or_needed(q)

        if category == "attestation":
            return _blank_or_needed(q)

        # custom
        banked = p.bank.get(normalize_question_key(label))
        if banked not in (None, ""):
            fitted = _fit(q, banked)
            if fitted is not None:
                return _entry(fitted, "bank", confirmed=True)
        if q.get("type") in ("text", "textarea") and q.get("required"):
            return None  # AI draft
        return _blank_or_needed(q)


# --------------------------------------------------------------------------- AI drafting

def build_draft_prompt(questions: List[Dict[str, Any]], profile: ProfileView, job: JobContext) -> str:
    """Resume text + job description + questions. Nothing else about the customer."""
    items = [{"id": q["id"], "question": q["label"],
              "max_words": 150 if q.get("type") == "textarea" else 25} for q in questions]
    resume = (profile.resume_text or "")[:MAX_RESUME_CHARS]
    jd = (job.description or "")[:MAX_JD_CHARS]
    return (
        f"Job: {job.title} at {job.company}\n\n"
        f"Job description:\n{jd}\n\n"
        f"Candidate resume:\n{resume}\n\n"
        "Draft answers to these application questions, written in the first person as the candidate. "
        "Use only facts stated in the resume; do not invent employers, titles, dates, numbers or credentials. "
        "If the resume does not support an answer, return an empty string for that id. "
        "Keep each answer within max_words.\n\n"
        f"Questions (JSON): {json.dumps(items)}\n\n"
        "Respond with only a JSON object mapping each id to its answer string."
    )


def parse_draft_response(text: str, ids: List[str]) -> Dict[str, str]:
    if not text:
        return {}
    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}
    try:
        data = json.loads(match.group(0))
    except ValueError:
        return {}
    return {k: str(v) for k, v in data.items() if k in ids and isinstance(v, (str, int, float))}


def draft_with_ai(questions: List[Dict[str, Any]], profile: ProfileView, job: JobContext) -> Dict[str, str]:
    if not questions or not profile.resume_text:
        return {}
    from services import ai_service

    prompt = build_draft_prompt(questions, profile, job)
    system = ("You help a job candidate draft truthful, concise answers to application questions. "
              "The candidate reviews every draft before it is used.")
    text = ai_service.complete_text(system, prompt, max_tokens=1500, feature="auto_apply_draft")
    return parse_draft_response(text, [q["id"] for q in questions])
