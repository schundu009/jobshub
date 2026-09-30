"""
FormSchemaService: read a job's public application form and normalize it.

Read-only. Sources:
- Greenhouse: GET boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}?questions=true
- Lever:      GET jobs.lever.co/{site}/{id}/apply (HTML; standard fields + "cards")
- Ashby:      GET api.ashbyhq.com/posting-api/job-board/{org} (posting exists), then
              the public job-board GraphQL read query (ApiJobPosting) that the
              Ashby careers page itself uses for the form. Falls back to the
              standard Ashby fields if the form is not readable.

Normalized question:
  {id, label, type, required, options[], category, description}
  type: text|textarea|select|multiselect|boolean|file|date|number
  category: identity|links|resume|cover_letter|work_auth|sponsorship|relocation|
            salary|start_date|eeo|attestation|custom

Cached per job in job_form_schemas for SCHEMA_TTL_HOURS.
"""
import html as html_lib
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

import httpx

from services.apply.ats import AtsRef, detect_ats
from services.apply.constants import SCHEMA_TTL_HOURS

logger = logging.getLogger(__name__)

USER_AGENT = "CariaraBot/1.0 (+https://cariara.com; read-only form schema)"
HTTP_TIMEOUT = 15.0


class SchemaFetchError(Exception):
    """The ATS could not be read (network error, closed posting, bad payload)."""

    def __init__(self, message: str, closed: bool = False):
        super().__init__(message)
        self.closed = closed


# --------------------------------------------------------------------------- classification

_RULES = [
    ("eeo", re.compile(r"gender|\brace\b|racial|ethnic|hispanic|latin[oax]|veteran|disabilit|sexual orientation|transgender", re.I)),
    ("resume", re.compile(r"\bresume\b|résumé|\bcv\b", re.I)),
    ("cover_letter", re.compile(r"cover letter", re.I)),
    ("attestation", re.compile(
        r"arbitrat|ai policy|privacy|consent|acknowledg|\bi agree\b|agree to|\bcertify|attest|background check|"
        r"terms and conditions|terms of (use|service)|gdpr|notetaker|brighthire|\brecord(ed|ing)?\b|"
        r"data (processing|retention)|truthful|accurate and complete", re.I)),
    ("sponsorship", re.compile(r"sponsor|\bvisa\b|h-?1b|immigration", re.I)),
    ("work_auth", re.compile(
        r"authori[sz]ed to work|legally (authori[sz]ed|eligible|able|permitted) to work|eligible to work|"
        r"work authori[sz]ation|right to work|permitted to work", re.I)),
    ("relocation", re.compile(r"relocat", re.I)),
    ("salary", re.compile(
        r"salary|compensation|pay expectation|expected pay|desired pay|pay range|expected (base|total)|rate expectation", re.I)),
    ("start_date", re.compile(
        r"earliest.*start|start date|when (can|could|would) you (start|begin)|available to start|"
        r"availability to start|notice period|how soon", re.I)),
    ("links", re.compile(r"linkedin|github|portfolio|website|personal site|twitter|\burl\b|\bblog\b", re.I)),
    ("identity", re.compile(
        r"^\s*(first|last|full|legal|preferred)\s*name|^\s*name\s*$|^\s*your name|e-?mail|phone|mobile|"
        r"address|\bcity\b|zip|postal|countr(y|ies) (where )?you (currently )?(reside|live)|where you (currently )?reside|"
        r"current location|^\s*location\s*$|where are you (located|based)|state of residence", re.I)),
]


def classify(label: str, qid: str = "") -> str:
    text = f"{label or ''}"
    for category, regex in _RULES:
        if regex.search(text):
            return category
    hint = (qid or "").lower()
    if hint in ("first_name", "last_name", "email", "phone", "name", "location"):
        return "identity"
    if hint in ("resume", "resume_text"):
        return "resume"
    if hint in ("cover_letter", "cover_letter_text"):
        return "cover_letter"
    return "custom"


# --------------------------------------------------------------------------- helpers

_TAG_RE = re.compile(r"<[^>]+>")


def _plain(text: Optional[str], limit: int = 600) -> Optional[str]:
    if not text:
        return None
    t = html_lib.unescape(html_lib.unescape(text))
    t = _TAG_RE.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return (t[: limit - 1] + "…") if len(t) > limit else (t or None)


def _clean_label(label: str) -> str:
    label = (label or "").replace("✱", "").replace("*", "")
    return re.sub(r"\s+", " ", label).strip()


def _question(qid, label, qtype, required, options=None, description=None, category=None) -> Dict[str, Any]:
    label = _clean_label(label)
    return {
        "id": str(qid),
        "label": label,
        "type": qtype,
        "required": bool(required),
        "options": [str(o) for o in (options or []) if str(o).strip()],
        "category": category or classify(label, str(qid)),
        "description": description,
    }


def _prettify(label: str) -> str:
    # "VeteranStatus" -> "Veteran Status"
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", label or "").strip()


# --------------------------------------------------------------------------- Greenhouse

_GH_TYPES = {
    "input_text": "text",
    "textarea": "textarea",
    "input_file": "file",
    "multi_value_single_select": "select",
    "multi_value_multi_select": "multiselect",
    "boolean": "boolean",
}


def normalize_greenhouse(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    questions: List[Dict[str, Any]] = []
    seen = set()

    def add(q):
        if q["id"] not in seen:
            seen.add(q["id"])
            questions.append(q)

    def from_gh(q, category=None):
        fields = [f for f in (q.get("fields") or []) if f.get("type") != "input_hidden"]
        if not fields:
            return None
        # Resume/cover letter come as input_file + textarea: prefer the file.
        primary = next((f for f in fields if f.get("type") == "input_file"), fields[0])
        qtype = _GH_TYPES.get(primary.get("type"), "text")
        options = [v.get("label") for v in (primary.get("values") or []) if v.get("label") is not None]
        label = q.get("label") or primary.get("name")
        if category == "eeo":
            label = _prettify(label)
        return _question(primary["name"], label, qtype, q.get("required"), options,
                         _plain(q.get("description")), category)

    for q in data.get("questions") or []:
        item = from_gh(q)
        if item:
            add(item)
    for q in data.get("location_questions") or []:
        item = from_gh(q)
        if item:
            add(item)
    for section in data.get("compliance") or []:
        for q in section.get("questions") or []:
            item = from_gh(q, category="eeo")
            if item:
                add(item)

    demographic = data.get("demographic_questions") or {}
    for q in demographic.get("questions") or []:
        options = [o.get("label") for o in (q.get("answer_options") or []) if o.get("label")]
        qtype = "multiselect" if q.get("type") == "multi_value_multi_select" else "select"
        add(_question(f"demographic_{q.get('id')}", q.get("label"), qtype, q.get("required"), options,
                      None, "eeo"))

    for dc in data.get("data_compliance") or []:
        if dc.get("requires_consent") or dc.get("requires_processing_consent"):
            add(_question("gdpr_processing_consent", "Consent to the processing of my personal data",
                          "boolean", True, [], None, "attestation"))
        if dc.get("requires_retention_consent"):
            add(_question("gdpr_retention_consent", "Consent to the retention of my personal data",
                          "boolean", True, [], None, "attestation"))
    return questions


# --------------------------------------------------------------------------- Lever

_LEVER_CARD_TYPES = {
    "text": "text",
    "textarea": "textarea",
    "multiple-choice": "select",
    "multiple-select": "multiselect",
    "dropdown": "select",
    "checkbox": "multiselect",
    "date": "date",
    "number": "number",
    "file-upload": "file",
}

_LEVER_EEO_LABELS = {"gender": "Gender", "race": "Race", "veteran": "Veteran status", "disability": "Disability status"}


def normalize_lever(page_html: str) -> List[Dict[str, Any]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_html, "lxml")
    form = soup.find("form") or soup
    questions: List[Dict[str, Any]] = []
    seen = set()

    def add(q):
        if q["id"] not in seen:
            seen.add(q["id"])
            questions.append(q)

    for li in form.select("li.application-question"):
        controls = [c for c in li.find_all(["input", "select", "textarea"])
                    if c.get("name") and c.get("type") != "hidden"]
        if not controls or controls[0]["name"].startswith("cards["):
            continue
        ctrl = controls[0]
        name = ctrl["name"]
        label_el = li.select_one(".application-label")
        label = label_el.get_text(" ", strip=True) if label_el else name
        required = bool(li.select_one(".required")) or ctrl.has_attr("required")
        options: List[str] = []
        if ctrl.name == "textarea":
            qtype = "textarea"
        elif ctrl.name == "select":
            qtype = "select"
            options = [o.get_text(strip=True) for o in ctrl.find_all("option") if o.get("value")]
        elif ctrl.get("type") == "file":
            qtype = "file"
        elif ctrl.get("type") in ("radio", "checkbox"):
            qtype = "select" if ctrl.get("type") == "radio" else "multiselect"
            options = [c.get("value") for c in controls if c.get("name") == name and c.get("value")]
        else:
            qtype = "text"
        add(_question(name, label, qtype, required, options))

    for inp in form.select('input[name$="[baseTemplate]"]'):
        m = re.match(r"cards\[([^\]]+)\]\[baseTemplate\]", inp.get("name", ""))
        if not m:
            continue
        try:
            template = json.loads(inp.get("value") or "{}")
        except ValueError:
            continue
        for i, field in enumerate(template.get("fields") or []):
            options = [o.get("text") for o in (field.get("options") or []) if o.get("text")]
            add(_question(
                f"cards[{m.group(1)}][field{i}]", field.get("text"),
                _LEVER_CARD_TYPES.get(field.get("type"), "text"), field.get("required"),
                options, _plain(field.get("description")),
            ))

    for sel in form.select('select[name^="eeo["]'):
        key = re.sub(r"^eeo\[|\]$", "", sel["name"])
        options = [o.get_text(strip=True) for o in sel.find_all("option") if o.get("value")]
        add(_question(sel["name"], _LEVER_EEO_LABELS.get(key, key.title()), "select", False, options, None, "eeo"))

    comments = form.select_one('textarea[name="comments"]')
    if comments is not None:
        add(_question("comments", "Additional information", "textarea", False, [], None, "cover_letter"))
    return questions


# --------------------------------------------------------------------------- Ashby

_ASHBY_TYPES = {
    "String": "text",
    "Email": "text",
    "Phone": "text",
    "LongText": "textarea",
    "File": "file",
    "ValueSelect": "select",
    "MultiValueSelect": "multiselect",
    "Boolean": "boolean",
    "Date": "date",
    "Number": "number",
    "Location": "text",
    "SocialLink": "text",
}

ASHBY_STANDARD_FIELDS = [
    ("_systemfield_name", "Name", "text", True),
    ("_systemfield_email", "Email", "text", True),
    ("_systemfield_phone", "Phone", "text", False),
    ("_systemfield_resume", "Resume", "file", True),
    ("_systemfield_linkedin", "LinkedIn", "text", False),
]


def _ashby_entries(form: Dict[str, Any], category: Optional[str] = None) -> List[Dict[str, Any]]:
    out = []
    for section in (form or {}).get("sections") or []:
        for entry in section.get("fieldEntries") or []:
            field = entry.get("field") or {}
            if not field or field.get("isDeactivated"):
                continue
            options = [v.get("label") for v in (field.get("selectableValues") or []) if v.get("label")]
            out.append(_question(
                field.get("path") or field.get("id"), field.get("title"),
                _ASHBY_TYPES.get(field.get("type"), "text"), entry.get("isRequired"),
                options, _plain(entry.get("descriptionHtml")), category,
            ))
    return out


def normalize_ashby(form_payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    posting = ((form_payload or {}).get("data") or {}).get("jobPosting") or {}
    questions = _ashby_entries(posting.get("applicationForm") or {})
    for survey in posting.get("surveyForms") or []:
        questions.extend(_ashby_entries(survey, category="eeo"))
    if not questions:
        questions = [_question(i, l, t, r) for i, l, t, r in ASHBY_STANDARD_FIELDS]
    seen, unique = set(), []
    for q in questions:
        if q["id"] not in seen:
            seen.add(q["id"])
            unique.append(q)
    return unique


ASHBY_FORM_QUERY = (
    "query ApiJobPosting($organizationHostedJobsPageName: String!, $jobPostingId: String!) {"
    " jobPosting(organizationHostedJobsPageName: $organizationHostedJobsPageName, jobPostingId: $jobPostingId) {"
    " id title"
    " applicationForm { id sections { title fieldEntries { ... on FormFieldEntry { id field isRequired descriptionHtml } } } }"
    " surveyForms { id sections { title fieldEntries { ... on FormFieldEntry { id field isRequired descriptionHtml } } } }"
    " } }"
)


# --------------------------------------------------------------------------- HTTP (patched in tests)

def http_get(url: str, params: Optional[dict] = None) -> httpx.Response:
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        return client.get(url, params=params)


def http_post_json(url: str, payload: dict) -> httpx.Response:
    """Only used for Ashby's public read-only GraphQL form query."""
    with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
        return client.post(url, json=payload)


def _check(resp: httpx.Response, what: str) -> httpx.Response:
    if resp.status_code == 404:
        raise SchemaFetchError(f"{what}: posting no longer available", closed=True)
    if resp.status_code >= 400:
        raise SchemaFetchError(f"{what}: HTTP {resp.status_code}")
    return resp


def fetch_greenhouse(ref: AtsRef) -> List[Dict[str, Any]]:
    url = f"https://boards-api.greenhouse.io/v1/boards/{ref.board}/jobs/{ref.posting_id}"
    resp = _check(http_get(url, params={"questions": "true"}), "Greenhouse")
    return normalize_greenhouse(resp.json())


def fetch_lever(ref: AtsRef) -> List[Dict[str, Any]]:
    resp = _check(http_get(f"https://jobs.lever.co/{ref.board}/{ref.posting_id}/apply"), "Lever")
    questions = normalize_lever(resp.text)
    if not questions:
        raise SchemaFetchError("Lever: application form not found")
    return questions


def fetch_ashby(ref: AtsRef) -> List[Dict[str, Any]]:
    board = _check(http_get(f"https://api.ashbyhq.com/posting-api/job-board/{ref.board}",
                            params={"includeCompensation": "true"}), "Ashby").json()
    if not any(str(j.get("id")) == str(ref.posting_id) for j in board.get("jobs") or []):
        raise SchemaFetchError("Ashby: posting no longer available", closed=True)
    payload = None
    try:
        resp = http_post_json(
            "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobPosting",
            {"operationName": "ApiJobPosting", "query": ASHBY_FORM_QUERY,
             "variables": {"organizationHostedJobsPageName": ref.board, "jobPostingId": ref.posting_id}},
        )
        if resp.status_code < 400:
            payload = resp.json()
    except Exception as e:  # fall back to standard fields
        logger.info("Ashby form definition unavailable for %s/%s: %s", ref.board, ref.posting_id, e)
    return normalize_ashby(payload)


FETCHERS: Dict[str, Callable[[AtsRef], List[Dict[str, Any]]]] = {
    "greenhouse": fetch_greenhouse,
    "lever": fetch_lever,
    "ashby": fetch_ashby,
}


# --------------------------------------------------------------------------- service

class FormSchemaResult:
    def __init__(self, ats, apply_url, supported, questions, error=None, closed=False):
        self.ats = ats
        self.apply_url = apply_url
        self.supported = supported
        self.questions = questions or []
        self.error = error
        self.closed = closed


def get_form_schema(db, job, force: bool = False) -> FormSchemaResult:
    """Normalized schema for a job, from the 24h DB cache or the ATS."""
    from models import JobFormSchema

    ref = detect_ats(job)
    apply_url = ref.apply_url or job.job_url
    if not ref.supported:
        return FormSchemaResult(ref.ats, apply_url, False, [], None)

    row = db.query(JobFormSchema).filter(JobFormSchema.job_id == job.id).first()
    fresh = row and row.fetched_at and row.fetched_at > datetime.utcnow() - timedelta(hours=SCHEMA_TTL_HOURS)
    if row and fresh and not force and row.supported and row.questions:
        return FormSchemaResult(row.ats, row.apply_url or apply_url, True, row.questions)

    try:
        questions = FETCHERS[ref.ats](ref)
        error, closed = None, False
    except SchemaFetchError as e:
        questions, error, closed = [], str(e), e.closed
    except Exception as e:  # network / parse errors
        logger.warning("form schema fetch failed for job %s: %s", job.id, e)
        questions, error, closed = [], f"{ref.ats}: could not read application form", False

    if row is None:
        row = JobFormSchema(job_id=job.id)
        db.add(row)
    row.ats = ref.ats
    row.apply_url = apply_url
    row.supported = error is None
    row.questions = questions
    row.error = error
    row.fetched_at = datetime.utcnow()
    db.flush()
    return FormSchemaResult(ref.ats, apply_url, True, questions, error, closed)
