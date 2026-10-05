"""
Cariara Auto Apply (Phase 1) tests.

No network: ATS responses come from recorded fixtures in tests/fixtures/apply
(recorded 2026-09-29 with one-time GETs; the Lever page is trimmed to its
<form> and long option lists are cut to 25), the capra-backend plan check and
the AI provider are mocked.
"""
import json
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from sqlalchemy.orm import Session

from models import (
    Application, ApplicationEvent, ApplyPreference, ApplyQueueItem,
    Company, Job, JobFormSchema, User, UserDocument,
)
from services.apply import ats as ats_mod
from services.apply import form_schema
from services.apply.form_schema import classify, normalize_ashby, normalize_greenhouse, normalize_lever
from services.apply.resolver import AnswerResolver, JobContext, ProfileView
from utils.security import create_access_token, hash_password

FIXTURES = Path(__file__).parent / "fixtures" / "apply"

GH_ANTHROPIC_URL = "https://job-boards.greenhouse.io/anthropic/jobs/4461450008"
GH_STRIPE_URL = "https://stripe.com/jobs/search?gh_jid=8172487"
LEVER_URL = "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd"
ASHBY_URL = "https://jobs.ashbyhq.com/anyscale/02698dc0-9416-425f-a13d-0938ffd229a8"
WORKDAY_URL = "https://acme.wd5.myworkdayjobs.com/en-US/External/job/Remote/Engineer_JR1"


def load_json(name):
    return json.loads((FIXTURES / name).read_text())


def headers(user):
    token, _ = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


def session_factory(db):
    return lambda: Session(bind=db.get_bind())


# --------------------------------------------------------------------------- network / AI fakes

class FakeHTTP:
    """Serves recorded fixtures; any other URL fails the test (no network)."""

    def __init__(self):
        self.calls = []

    def get(self, url, params=None):
        self.calls.append(("GET", url))
        routes = {
            "https://boards-api.greenhouse.io/v1/boards/anthropic/jobs/4461450008": ("json", "gh_anthropic.json"),
            "https://boards-api.greenhouse.io/v1/boards/stripe/jobs/8172487": ("json", "gh_stripe.json"),
            "https://jobs.lever.co/palantir/6ed76ce8-4156-4b60-b120-403538bd66cd/apply": ("html", "lever_palantir_apply.html"),
            "https://api.ashbyhq.com/posting-api/job-board/anyscale": ("json", "ashby_anyscale_board.json"),
        }
        if url not in routes:
            raise AssertionError(f"unexpected network GET {url}")
        kind, name = routes[url]
        body = (FIXTURES / name).read_bytes()
        return httpx.Response(200, content=body, request=httpx.Request("GET", url),
                              headers={"content-type": "application/json" if kind == "json" else "text/html"})

    def post_json(self, url, payload):
        self.calls.append(("POST", url))
        assert url.startswith("https://jobs.ashbyhq.com/api/non-user-graphql"), url
        assert "mutation" not in payload["query"].lower()  # read-only query only
        return httpx.Response(200, content=(FIXTURES / "ashby_anyscale_form.json").read_bytes(),
                              request=httpx.Request("POST", url))


class FakeAI:
    def __init__(self, fail=False):
        self.prompts = []
        self.features = []
        self.fail = fail

    def __call__(self, system, prompt, max_tokens=1000, feature=None):
        self.prompts.append(prompt)
        self.features.append(feature)
        if self.fail:
            raise ValueError("Anthropic API key not configured")
        ids = [item["id"] for item in json.loads(prompt.split("Questions (JSON): ", 1)[1].split("\n\n")[0])]
        return json.dumps({qid: f"Draft answer for {qid}" for qid in ids})


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    http = FakeHTTP()
    monkeypatch.setattr(form_schema, "http_get", http.get)
    monkeypatch.setattr(form_schema, "http_post_json", http.post_json)
    monkeypatch.setitem(ats_mod._registry_cache, "stripe", ("greenhouse", "stripe"))
    return http


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    from services import ai_service
    ai = FakeAI()
    monkeypatch.setattr(ai_service, "complete_text", ai)
    return ai


# --------------------------------------------------------------------------- data fixtures

def make_user(db, email, paid=True, **profile):
    fields = dict(first_name="Ada", last_name="Lovelace", phone="+1 555 0100", city="New York", state="NY",
                  address_country="United States", linkedin_url="https://linkedin.com/in/ada",
                  us_authorized="yes", requires_sponsorship="no", willing_to_relocate="no",
                  job_titles=["Account Executive"], skills="python, kubernetes")
    fields.update(profile)
    user = User(email=email, name="Ada", is_active=True, password_hash=hash_password("Test-password-123"), **fields)
    db.add(user)
    db.commit()
    db.add(UserDocument(user_id=user.id, document_type="resume", filename="ada_resume.pdf", is_default=True,
                        content_text="Ada Lovelace. Account Executive at Analytical Engines Inc. Sold API "
                                     "products to engineering teams. Python, Kubernetes."))
    if paid:
        db.add(ApplyPreference(user_id=user.id, plan_override="pro"))
    db.commit()
    return user


@pytest.fixture
def paid(db):
    return make_user(db, "paid@example.com")


@pytest.fixture
def free(db):
    return make_user(db, "free@example.com", paid=False)


def make_job(db, url, title="Account Executive", company="Anthropic", source=None, external_id=None,
             location="New York, NY", days_old=1, description="Sell our API to engineering teams. Python."):
    comp = db.query(Company).filter(Company.name == company).first()
    if not comp:
        comp = Company(name=company)
        db.add(comp)
        db.flush()
    job = Job(title=title, company_id=comp.id, job_url=url, source=source, external_job_id=external_id,
              location=location, is_active=True, job_description=description,
              posted_date=datetime.utcnow() - timedelta(days=days_old))
    db.add(job)
    db.commit()
    return job


@pytest.fixture
def gh_job(db):
    return make_job(db, GH_ANTHROPIC_URL, external_id="4461450008")


@pytest.fixture
def ashby_job(db):
    return make_job(db, ASHBY_URL, title="Enterprise Account Executive", company="Anyscale")


def events_of(db, app_id):
    return [e.type for e in db.query(ApplicationEvent).filter_by(application_id=app_id).order_by(ApplicationEvent.id)]


# =========================================================================== schema normalization

def by_id(questions):
    return {q["id"]: q for q in questions}


def test_greenhouse_anthropic_schema():
    qs = by_id(normalize_greenhouse(load_json("gh_anthropic.json")))
    assert qs["first_name"]["category"] == "identity" and qs["first_name"]["required"]
    assert qs["resume"]["type"] == "file" and qs["resume"]["category"] == "resume"
    assert qs["question_8581812008"]["category"] == "links"
    assert qs["question_8581811008"]["category"] == "sponsorship"
    assert qs["question_8581811008"]["options"] == ["Yes", "No"]
    assert qs["question_8581805008"]["category"] == "start_date"
    assert qs["question_8581808008"] == {**qs["question_8581808008"], "type": "textarea", "category": "custom"}
    for attest in ("question_8581807008", "question_18371138008", "question_18374300008"):
        assert qs[attest]["category"] == "attestation"
    # EEOC compliance section
    for eeo in ("veteran_status", "race", "gender"):
        assert qs[eeo]["category"] == "eeo" and not qs[eeo]["required"]
    assert qs["veteran_status"]["label"] == "Veteran Status"
    assert any("wish to answer" in o for o in qs["veteran_status"]["options"])


def test_greenhouse_stripe_schema():
    qs = by_id(normalize_greenhouse(load_json("gh_stripe.json")))
    assert "longitude" not in qs and "latitude" not in qs  # input_hidden skipped
    assert qs["location"]["category"] == "identity"
    assert qs["cover_letter"]["category"] == "cover_letter" and not qs["cover_letter"]["required"]
    assert qs["question_68935297[]"]["type"] == "multiselect"
    assert qs["question_68935296"]["category"] == "identity" and len(qs["question_68935296"]["options"]) > 10
    assert qs["question_68935298"]["category"] == "work_auth"
    assert qs["question_68935299"]["category"] == "sponsorship"
    assert qs["question_69457836"]["category"] == "attestation"  # BrightHire recording consent
    assert all(q["type"] in ("text", "textarea", "select", "multiselect", "boolean", "file", "date", "number")
               for q in qs.values())


def test_lever_schema():
    qs = normalize_lever((FIXTURES / "lever_palantir_apply.html").read_text())
    ids = by_id(qs)
    assert ids["resume"]["type"] == "file" and ids["resume"]["required"]
    assert ids["name"]["label"] == "Full name" and ids["name"]["category"] == "identity"
    assert ids["email"]["required"] and not ids["phone"]["required"]
    assert ids["urls[LinkedIn]"]["category"] == "links"
    assert ids["comments"]["type"] == "textarea"
    def cat(prefix):
        return next(q["category"] for q in qs if q["label"].startswith(prefix))
    assert cat("Are you legally authorized to work") == "work_auth"
    assert cat("Will you now or in the future require sponsorship") == "sponsorship"
    assert cat("As part of our interview process, we may use AI notetakers") == "attestation"
    lang = next(q for q in qs if q["label"].startswith("Language Skill"))
    assert lang["type"] == "multiselect" and lang["required"] and lang["id"].startswith("cards[")
    uni = next(q for q in qs if q["label"].startswith("Which university"))
    assert uni["type"] == "select" and uni["options"]


def test_ashby_schema_and_fallback():
    qs = by_id(normalize_ashby(load_json("ashby_anyscale_form.json")))
    assert qs["_systemfield_name"]["category"] == "identity"
    assert qs["_systemfield_resume"]["type"] == "file"
    sponsor = next(q for q in qs.values() if q["category"] == "sponsorship")
    assert sponsor["type"] == "select" and sponsor["options"] == ["Yes", "No"] and sponsor["required"]
    fallback = normalize_ashby(None)
    assert [q["id"] for q in fallback][:2] == ["_systemfield_name", "_systemfield_email"]


@pytest.mark.parametrize("label,category", [
    ("First Name", "identity"), ("Email", "identity"), ("Phone number", "identity"),
    ("LinkedIn Profile", "links"), ("Website", "links"), ("Resume/CV", "resume"), ("Cover Letter", "cover_letter"),
    ("Are you legally authorized to work in the United States?", "work_auth"),
    ("Will you now or in the future require visa sponsorship?", "sponsorship"),
    ("Are you willing to relocate?", "relocation"), ("What are your salary expectations?", "salary"),
    ("When can you start?", "start_date"), ("What is your notice period?", "start_date"),
    ("Gender", "eeo"), ("Are you Hispanic/Latino?", "eeo"), ("Disability Status", "eeo"),
    ("Please read the arbitration agreement below", "attestation"), ("AI Policy for Application", "attestation"),
    ("I consent to a background check", "attestation"), ("Privacy notice acknowledgement", "attestation"),
    ("Why do you want to work here?", "custom"), ("How did you hear about us?", "custom"),
])
def test_classify(label, category):
    assert classify(label) == category


def test_detect_ats():
    class J:  # minimal job stand-in
        def __init__(self, url, source=None, external_job_id=None):
            self.job_url, self.source, self.external_job_id = url, source, external_job_id

    gh = ats_mod.detect_ats(J(GH_ANTHROPIC_URL))
    assert (gh.ats, gh.board, gh.posting_id, gh.supported) == ("greenhouse", "anthropic", "4461450008", True)
    custom = ats_mod.detect_ats(J(GH_STRIPE_URL, source="stripe"))
    assert (custom.ats, custom.board, custom.posting_id) == ("greenhouse", "stripe", "8172487")
    assert custom.apply_url == GH_STRIPE_URL
    embed = ats_mod.detect_ats(J("https://boards.greenhouse.io/embed/job_app?for=acme&token=123"))
    assert (embed.board, embed.posting_id) == ("acme", "123")
    lever = ats_mod.detect_ats(J(LEVER_URL))
    assert lever.ats == "lever" and lever.apply_url.endswith("/apply")
    ashby = ats_mod.detect_ats(J(ASHBY_URL))
    assert ashby.ats == "ashby" and ashby.apply_url.endswith("/application")
    wd = ats_mod.detect_ats(J(WORKDAY_URL))
    assert wd.ats == "workday" and not wd.supported


# =========================================================================== resolver

def profile(**overrides):
    base = dict(first_name="Ada", last_name="Lovelace", email="ada@example.com", phone="555", city="New York",
                state="NY", country="United States", linkedin="https://linkedin.com/in/ada",
                work_authorized_us=True, requires_sponsorship=False, willing_to_relocate=False,
                resume_filename="ada.pdf", resume_text="Ada resume text")
    base.update(overrides)
    return ProfileView(**base)


def resolve(questions, p=None, drafter=None):
    drafter = drafter or (lambda qs, pv, job: {q["id"]: "drafted" for q in qs})
    return AnswerResolver(p or profile(), JobContext("AE", "Anthropic", "JD"), ai_drafter=drafter).resolve(questions)


def test_resolver_fills_profile_answers():
    answers = resolve(normalize_greenhouse(load_json("gh_anthropic.json")))
    assert answers["first_name"] == {"value": "Ada", "source": "profile", "confirmed": True, "needs_user": False}
    assert answers["email"]["value"] == "ada@example.com"
    assert answers["resume"]["value"] == "ada.pdf"
    assert answers["question_8581812008"]["value"] == "https://linkedin.com/in/ada"
    assert answers["question_8581811008"]["value"] == "No"  # sponsorship from profile
    assert answers["question_8590525008"]["value"] == "No"  # relocation from profile


def test_resolver_eeo_opt_out_and_opt_in():
    qs = normalize_greenhouse(load_json("gh_anthropic.json"))
    out = resolve(qs, profile(eeo_opt_in=False, gender="female"))
    assert out["gender"]["value"] and "decline" in out["gender"]["value"].lower()
    assert "wish to answer" in out["veteran_status"]["value"]
    opted = resolve(qs, profile(eeo_opt_in=True, gender="Female"))
    assert opted["gender"]["value"] == "Female" and opted["gender"]["source"] == "profile"
    # Required EEO question without a decline option -> needs_user
    q = [{"id": "g", "label": "Gender", "type": "select", "required": True, "options": ["Male", "Female"],
          "category": "eeo"}]
    assert resolve(q, profile(eeo_opt_in=False))["g"]["needs_user"] is True


def test_resolver_attestations_never_answered():
    answers = resolve(normalize_greenhouse(load_json("gh_anthropic.json")))
    for qid in ("question_8581807008", "question_18371138008", "question_18374300008"):
        assert answers[qid]["value"] is None and answers[qid]["needs_user"] is True
    lever = normalize_lever((FIXTURES / "lever_palantir_apply.html").read_text())
    notetaker = next(q for q in lever if q["category"] == "attestation")
    assert resolve(lever)[notetaker["id"]]["needs_user"] is True


def test_resolver_ai_drafts_and_unknown_facts():
    qs = normalize_greenhouse(load_json("gh_anthropic.json"))
    answers = resolve(qs)
    why = answers["question_8581808008"]
    assert why == {"value": "drafted", "source": "ai_draft", "confirmed": False, "needs_user": False}
    # optional free text is left blank, not drafted
    assert answers["question_8581809008"]["value"] is None and not answers["question_8581809008"]["needs_user"]
    # custom required select -> needs_user (no guessing)
    assert answers["question_9019066008"]["needs_user"] is True
    # unknown sponsorship status -> needs_user, never guessed
    unknown = resolve(qs, profile(requires_sponsorship=None))
    assert unknown["question_8581811008"]["needs_user"] is True and unknown["question_8581811008"]["value"] is None
    # AI failure -> required free text needs the user
    def boom(*_):
        raise ValueError("no key")
    failed = resolve(qs, drafter=boom)
    assert failed["question_8581808008"]["needs_user"] is True


def test_resolver_uses_answer_bank_for_custom():
    qs = normalize_greenhouse(load_json("gh_anthropic.json"))
    p = profile(bank={"have you ever interviewed at anthropic before": "No"})
    assert resolve(qs, p)["question_9019066008"] == {"value": "No", "source": "bank", "confirmed": True,
                                                     "needs_user": False}


def test_ai_prompt_contains_resume_and_jd_only(fake_ai):
    from services.apply.resolver import draft_with_ai
    q = [{"id": "q1", "label": "Why us?", "type": "textarea", "required": True, "category": "custom"}]
    result = draft_with_ai(q, profile(resume_text="RESUME-BODY"), JobContext("AE", "Anthropic", "JD-BODY"))
    assert result == {"q1": "Draft answer for q1"}
    prompt = fake_ai.prompts[0]
    assert "RESUME-BODY" in prompt and "JD-BODY" in prompt and "Why us?" in prompt
    assert "password" not in prompt.lower() and "ada@example.com" not in prompt
    assert fake_ai.features == ["auto_apply_draft"]  # routed to the cheap drafting model


# =========================================================================== API: plan gating / caps / uniqueness

def test_free_user_can_read_but_not_enable_or_create(client, free, gh_job):
    h = headers(free)
    prefs = client.get("/api/apply/preferences", headers=h)
    assert prefs.status_code == 200
    body = prefs.json()
    assert body["plan_ok"] is False and body["enabled"] is False and body["mode"] == "review"
    assert body["min_match_score"] == 70 and body["ats_allowlist"] == ["greenhouse", "lever", "ashby"]
    assert body["target_roles"] == ["Account Executive"]  # seeded from the user's settings
    for payload in ({"enabled": True}, {"mode": "auto"}):
        r = client.put("/api/apply/preferences", json=payload, headers=h)
        assert r.status_code == 402 and r.json() == {"detail": "Auto Apply is available on paid plans"}
    assert client.put("/api/apply/preferences", json={"min_match_score": 80}, headers=h).json()["min_match_score"] == 80
    r = client.post("/api/apply/applications", json={"job_id": gh_job.id}, headers=h)
    assert r.status_code == 402 and r.json()["detail"] == "Auto Apply is available on paid plans"
    assert client.get("/api/apply/queue", headers=h).status_code == 200
    assert client.get("/api/apply/readiness", headers=h).json()["plan_ok"] is False


def test_paid_preferences_roundtrip(client, paid):
    h = headers(paid)
    r = client.put("/api/apply/preferences", headers=h, json={
        "enabled": True, "mode": "auto", "daily_cap": 999, "ats_allowlist": ["greenhouse"],
        "excluded_companies": [" Acme ", ""]})
    assert r.status_code == 422  # daily_cap above validation bound
    r = client.put("/api/apply/preferences", headers=h, json={
        "enabled": True, "mode": "auto", "daily_cap": 100, "ats_allowlist": ["greenhouse"],
        "excluded_companies": [" Acme ", ""]})
    body = r.json()
    assert r.status_code == 200 and body["enabled"] and body["mode"] == "auto" and body["plan_ok"]
    assert body["daily_cap"] == body["daily_cap_max"] == 25  # clamped to the plan maximum
    assert body["excluded_companies"] == ["Acme"] and body["ats_allowlist"] == ["greenhouse"]
    assert client.put("/api/apply/preferences", headers=h, json={"ats_allowlist": ["workday"]}).status_code == 422


def test_daily_cap_429(client, db, paid):
    h = headers(paid)
    client.put("/api/apply/preferences", headers=h, json={"daily_cap": 1})
    first = make_job(db, GH_ANTHROPIC_URL, external_id="4461450008")
    second = make_job(db, ASHBY_URL, company="Anyscale")
    assert client.post("/api/apply/applications", json={"job_id": first.id}, headers=h).status_code == 201
    r = client.post("/api/apply/applications", json={"job_id": second.id}, headers=h)
    assert r.status_code == 429
    assert "Daily limit" in r.json()["detail"] and r.json()["resets_at"].endswith("Z")
    assert client.get("/api/apply/stats", headers=h).json()["today_count"] == 1


def test_unique_application_409(client, paid, gh_job):
    h = headers(paid)
    created = client.post("/api/apply/applications", json={"job_id": gh_job.id}, headers=h)
    assert created.status_code == 201
    dup = client.post("/api/apply/applications", json={"job_id": gh_job.id}, headers=h)
    assert dup.status_code == 409 and dup.json()["id"] == created.json()["id"]


def test_other_users_application_is_404(client, db, paid, gh_job):
    app_id = client.post("/api/apply/applications", json={"job_id": gh_job.id}, headers=headers(paid)).json()["id"]
    other = make_user(db, "other@example.com")
    assert client.get(f"/api/apply/applications/{app_id}", headers=headers(other)).status_code == 404
    assert client.get("/api/apply/preferences").status_code == 401


# =========================================================================== API: review flow

def test_review_flow_end_to_end(client, db, paid, gh_job, fake_ai):
    h = headers(paid)
    r = client.post("/api/apply/applications", json={"job_id": gh_job.id}, headers=h)
    assert r.status_code == 201
    app = r.json()
    assert app["status"] == "needs_input" and app["ats"] == "greenhouse"
    assert app["match_score"] >= 70  # scored on creation even though it was not queued
    assert app["apply_url"] == GH_ANTHROPIC_URL and app["job"]["company_name"] == "Anthropic"
    assert app["documents"][0]["filename"] == "ada_resume.pdf" and app["resume_doc_id"] == app["documents"][0]["id"]
    q = {x["id"]: x for x in app["questions"]}
    assert q["first_name"]["answer"] == "Ada" and q["first_name"]["source"] == "profile"
    assert q["question_8581808008"]["source"] == "ai_draft" and not q["question_8581808008"]["confirmed"]
    assert q["question_18374300008"]["needs_user"] is True
    assert [e["type"] for e in app["events"]] == ["created", "needs_input"]
    assert len(fake_ai.prompts) == 1  # one batched AI call per application

    # approve blocked while questions need the user
    blocked = client.post(f"/api/apply/applications/{app['id']}/approve", headers=h)
    assert blocked.status_code == 400
    missing = blocked.json()["missing"]
    assert "question_18374300008" in missing and "question_8581808008" in missing  # unconfirmed AI draft too

    needs = [x for x in app["questions"] if x["needs_user"]]
    answers = {x["id"]: (x["options"][0] if x["options"] else "My answer") for x in needs}
    r = client.patch(f"/api/apply/applications/{app['id']}/answers", headers=h, json={"answers": answers})
    assert r.status_code == 200 and r.json()["status"] == "ready_for_review"
    still = client.post(f"/api/apply/applications/{app['id']}/approve", headers=h)
    assert still.status_code == 400 and set(still.json()["missing"]) == {
        x["id"] for x in app["questions"] if x["source"] == "ai_draft"}

    drafts = {x["id"]: x["answer"] for x in app["questions"] if x["source"] == "ai_draft"}
    r = client.patch(f"/api/apply/applications/{app['id']}/answers", headers=h, json={"answers": drafts})
    confirmed = {x["id"]: x for x in r.json()["questions"]}
    assert all(confirmed[i]["source"] == "user" and confirmed[i]["confirmed"] for i in drafts)

    approved = client.post(f"/api/apply/applications/{app['id']}/approve", headers=h)
    assert approved.status_code == 200 and approved.json()["status"] == "approved"

    handoff = client.post(f"/api/apply/applications/{app['id']}/handoff", headers=h)
    assert handoff.status_code == 200
    payload = handoff.json()
    assert payload["apply_url"] == GH_ANTHROPIC_URL
    prefill = {p["question_id"]: p for p in payload["prefill"]}
    assert prefill["first_name"]["value"] == "Ada" and prefill["first_name"]["label"] == "First Name"
    assert "cover_letter_text" in payload

    done = client.post(f"/api/apply/applications/{app['id']}/mark-submitted", headers=h,
                       json={"confirmation": "GH-123"})
    assert done.status_code == 200 and done.json()["status"] == "submitted"
    assert done.json()["confirmation"] == "GH-123" and done.json()["submitted_at"]
    types = events_of(db, app["id"])
    assert types == ["created", "needs_input", "answers_updated", "answers_updated", "approved", "handed_off",
                     "submitted"]
    # answers are frozen once submitted
    assert client.patch(f"/api/apply/applications/{app['id']}/answers", headers=h,
                        json={"answers": {"first_name": "X"}}).status_code == 409


def test_handoff_requires_approval_and_unknown_answers_rejected(client, paid, gh_job):
    h = headers(paid)
    app = client.post("/api/apply/applications", json={"job_id": gh_job.id}, headers=h).json()
    assert client.post(f"/api/apply/applications/{app['id']}/handoff", headers=h).status_code == 409
    r = client.patch(f"/api/apply/applications/{app['id']}/answers", headers=h, json={"answers": {"nope": 1}})
    assert r.status_code == 400 and r.json()["missing"] == ["nope"]


def test_skip_retry_and_list(client, db, paid, gh_job, no_network):
    h = headers(paid)
    app = client.post("/api/apply/applications", json={"job_id": gh_job.id}, headers=h).json()
    skipped = client.post(f"/api/apply/applications/{app['id']}/skip", headers=h, json={"reason": "Not a fit"})
    assert skipped.json()["status"] == "skipped" and skipped.json()["events"][-1]["message"] == "Not a fit"
    gh_calls = len([c for c in no_network.calls if "greenhouse" in c[1]])
    retried = client.post(f"/api/apply/applications/{app['id']}/retry-draft", headers=h)
    assert retried.json()["status"] == "needs_input"
    assert len([c for c in no_network.calls if "greenhouse" in c[1]]) == gh_calls + 1  # forced refetch
    listing = client.get("/api/apply/applications?status=needs_input,ready_for_review", headers=h).json()
    assert listing["total"] == 1
    item = listing["items"][0]
    assert item["job"]["title"] == "Account Executive" and item["needs_user_count"] > 0 and item["ats"] == "greenhouse"
    assert client.get("/api/apply/applications?status=bogus", headers=h).status_code == 400
    stats = client.get("/api/apply/stats", headers=h).json()
    assert stats["by_status"] == {"needs_input": 1} and stats["daily_cap"] == 10


def test_schema_cached_between_applications(client, db, paid, no_network):
    h = headers(paid)
    job = make_job(db, GH_ANTHROPIC_URL, external_id="4461450008")
    client.post("/api/apply/applications", json={"job_id": job.id}, headers=h).json()
    other = make_user(db, "second@example.com")
    client.post("/api/apply/applications", json={"job_id": job.id}, headers=headers(other))
    assert len([c for c in no_network.calls if "greenhouse" in c[1]]) == 1
    assert db.query(JobFormSchema).filter_by(job_id=job.id).one().supported


def test_unsupported_and_closed_postings(client, db, paid, monkeypatch):
    h = headers(paid)
    wd = make_job(db, WORKDAY_URL, company="Acme")
    r = client.post("/api/apply/applications", json={"job_id": wd.id}, headers=h).json()
    assert r["status"] == "unsupported" and r["apply_url"] == WORKDAY_URL and r["ats"] == "workday"
    # manual apply is still recordable
    assert client.post(f"/api/apply/applications/{r['id']}/mark-submitted", headers=h).json()["status"] == "submitted"

    def gone(url, params=None):
        return httpx.Response(404, request=httpx.Request("GET", url))
    monkeypatch.setattr(form_schema, "http_get", gone)
    closed = make_job(db, "https://job-boards.greenhouse.io/anthropic/jobs/999", company="Anthropic")
    r = client.post("/api/apply/applications", json={"job_id": closed.id}, headers=h).json()
    assert r["status"] == "failed" and "no longer available" in r["events"][-1]["message"]


def test_patch_application_documents(client, db, paid, gh_job):
    h = headers(paid)
    app = client.post("/api/apply/applications", json={"job_id": gh_job.id}, headers=h).json()
    doc = UserDocument(user_id=paid.id, document_type="resume", filename="ada_v2.pdf", content_text="v2")
    db.add(doc)
    db.commit()
    r = client.patch(f"/api/apply/applications/{app['id']}", headers=h,
                     json={"resume_doc_id": doc.id, "cover_letter_text": "Dear team"})
    body = r.json()
    assert body["resume_doc_id"] == doc.id and body["cover_letter_text"] == "Dear team"
    assert {q["id"]: q for q in body["questions"]}["resume"]["answer"] == "ada_v2.pdf"
    stranger = UserDocument(user_id=make_user(db, "s@example.com").id, document_type="resume", filename="x.pdf")
    db.add(stranger)
    db.commit()
    assert client.patch(f"/api/apply/applications/{app['id']}", headers=h,
                        json={"resume_doc_id": stranger.id}).status_code == 404


# =========================================================================== auto mode & queue

def test_posting_key_ignores_location_copies_only():
    from services.apply.matching import posting_key

    def key(title, company="SpaceX"):
        return posting_key(Job(id=1, title=title, company=Company(name=company)))

    assert key("Sr. SRE (Starlink)") == key("Senior SRE (Starlink)")
    assert key("Software Engineer - Remote") == key("Software Engineer | Austin, TX") == key("Software Engineer (New York, NY)")
    assert key("Software Engineer, Backend, Payments") != key("Software Engineer")
    assert key("Software Engineer II") != key("Software Engineer")
    assert key("Software Engineer", "Acme") != key("Software Engineer")


def test_queue_and_applications_are_strictly_deduplicated(client, db, paid, monkeypatch):
    from tasks import apply_tasks
    monkeypatch.setattr(apply_tasks, "get_db", session_factory(db))
    h = headers(paid)
    ny = make_job(db, ASHBY_URL, title="Enterprise Account Executive", company="Anyscale")
    sf = make_job(db, ASHBY_URL.replace("-", "a", 1), title="Enterprise Account Executive - Remote",
                  company="Anyscale", location="San Francisco, CA", days_old=2)
    queue = client.get("/api/apply/queue", headers=h).json()["items"]
    assert len(queue) == 1 and queue[0]["job"]["id"] in (ny.id, sf.id)  # one item for the role
    assert "salary_min" in queue[0]["job"]
    kept = queue[0]["job"]["id"]
    other = sf.id if kept == ny.id else ny.id
    assert client.post("/api/apply/applications", json={"job_id": kept}, headers=h).status_code == 201
    r = client.post("/api/apply/applications", json={"job_id": other}, headers=h)
    assert r.status_code == 409 and "this role" in r.json()["detail"]
    assert client.get("/api/apply/queue", headers=h).json()["items"] == []


def test_queue_build_and_exclusions(client, db, paid, monkeypatch):
    from tasks import apply_tasks
    monkeypatch.setattr(apply_tasks, "get_db", session_factory(db))
    h = headers(paid)
    match = make_job(db, ASHBY_URL, title="Enterprise Account Executive", company="Anyscale")
    make_job(db, WORKDAY_URL, title="Account Executive", company="Acme")  # ATS not allowed
    make_job(db, LEVER_URL, title="Account Executive", company="Palantir", days_old=30)  # too old
    make_job(db, "https://jobs.lever.co/palantir/00000000-0000-0000-0000-000000000000", title="Chef",
             company="Palantir")  # no match
    queue = client.get("/api/apply/queue", headers=h).json()
    assert queue["generated_at"]
    assert [i["job"]["id"] for i in queue["items"]] == [match.id]
    item = queue["items"][0]
    assert item["job"]["ats"] == "ashby" and item["match_score"] >= 70
    assert any("Account Executive" in r for r in item["reasons"])
    client.post("/api/apply/applications", json={"job_id": match.id}, headers=h)
    assert client.get("/api/apply/queue", headers=h).json()["items"] == []  # applied jobs drop out

    client.put("/api/apply/preferences", headers=h, json={"excluded_companies": ["anyscale"]})
    monkeypatch.setattr(apply_tasks.refresh_queue_for_user, "apply_async",
                        lambda *a, **k: (_ for _ in ()).throw(ConnectionError("no broker")))
    assert client.post("/api/apply/queue/refresh", headers=h).json() == {"status": "queued"}
    assert db.query(ApplyQueueItem).filter_by(user_id=paid.id).count() == 0


def test_auto_mode_prepares_and_auto_approves(client, db, paid, monkeypatch):
    from tasks import apply_tasks
    monkeypatch.setattr(apply_tasks, "get_db", session_factory(db))
    h = headers(paid)
    assert client.put("/api/apply/preferences", headers=h,
                      json={"enabled": True, "mode": "auto", "daily_cap": 1}).status_code == 200
    ashby = make_job(db, ASHBY_URL, title="Enterprise Account Executive", company="Anyscale")
    gh = make_job(db, GH_ANTHROPIC_URL, external_id="4461450008", title="Account Executive")
    db.add_all([ApplyQueueItem(user_id=paid.id, job_id=ashby.id, match_score=95, reasons=[], ats="ashby"),
                ApplyQueueItem(user_id=paid.id, job_id=gh.id, match_score=90, reasons=[], ats="greenhouse")])
    db.commit()

    result = apply_tasks.prepare_for_user_sync(paid.id)
    assert result["created"] == 1  # daily cap of 1
    db.expire_all()
    app = db.query(Application).filter_by(user_id=paid.id).one()
    assert app.job_id == ashby.id and app.status == "approved" and app.created_by == "auto"
    assert events_of(db, app.id) == ["created", "auto_approved"]
    assert apply_tasks.prepare_for_user_sync(paid.id)["reason"] == "cap"

    # With room, the Greenhouse job (attestations) is prepared but waits for the user.
    client.put("/api/apply/preferences", headers=h, json={"daily_cap": 5})
    apply_tasks.prepare_for_user_sync(paid.id)
    db.expire_all()
    gh_app = db.query(Application).filter_by(user_id=paid.id, job_id=gh.id).one()
    assert gh_app.status == "needs_input"

    # Extension placeholders
    nxt = client.get("/api/apply/extension/next", headers=h).json()["application"]
    assert nxt["id"] == app.id and nxt["prefill"] and nxt["apply_url"].endswith("/application")
    r = client.post(f"/api/apply/applications/{app.id}/extension-result", headers=h, json={"status": "captcha"})
    assert r.json()["status"] == "handed_off" and r.json()["events"][-1]["type"] == "extension_captcha"
    r = client.post(f"/api/apply/applications/{app.id}/extension-result", headers=h,
                    json={"status": "submitted", "confirmation": "ok"})
    assert r.json()["status"] == "submitted" and r.json()["submitted_via"] == "extension"
    assert client.get("/api/apply/extension/next", headers=h).json() == {"application": None}


def test_extension_finds_the_application_for_the_page(client, db, paid):
    from routes.apply import _posting_key
    assert _posting_key("https://job-boards.greenhouse.io/anthropic/jobs/4461450008?gh_src=x") == \
        _posting_key("https://boards.greenhouse.io/embed/job_app?for=anthropic&token=1&gh_jid=4461450008") == \
        _posting_key("https://job-boards.greenhouse.io/embed/job_app?for=anthropic&token=4461450008") == \
        ("greenhouse", "4461450008")
    assert _posting_key("https://jobs.lever.co/acme/abc-123/apply") == _posting_key("https://jobs.lever.co/acme/abc-123")

    h = headers(paid)
    job = make_job(db, GH_ANTHROPIC_URL, external_id="4461450008", title="Account Executive")
    app = Application(user_id=paid.id, job_id=job.id, status="approved", apply_url=GH_ANTHROPIC_URL,
                      form_schema_snapshot=[{"id": "question_1", "label": "LinkedIn", "type": "text", "category": "custom"}],
                      answers={"question_1": {"value": "https://linkedin.com/in/me"}})
    db.add(app)
    db.commit()
    got = client.get("/api/apply/extension/for-url", headers=h,
                     params={"url": "https://job-boards.greenhouse.io/anthropic/jobs/4461450008#app"}).json()["application"]
    assert got["id"] == app.id
    assert got["prefill"] == [{"question_id": "question_1", "label": "LinkedIn", "value": "https://linkedin.com/in/me",
                               "type": "text", "category": "custom"}]
    other = client.get("/api/apply/extension/for-url", headers=h,
                       params={"url": "https://job-boards.greenhouse.io/anthropic/jobs/999999"}).json()
    assert other == {"application": None}


def test_extension_origin_is_allowed_by_cors(client):
    r = client.options("/api/apply/extension/for-url", headers={
        "Origin": "chrome-extension://abcdefghijklmnopabcdefghijklmnop",
        "Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "x-cariara-token"})
    assert r.headers.get("access-control-allow-origin") == "chrome-extension://abcdefghijklmnopabcdefghijklmnop"


def test_review_mode_never_auto_approves(client, db, paid, ashby_job):
    h = headers(paid)
    client.put("/api/apply/preferences", headers=h, json={"enabled": True, "mode": "review"})
    r = client.post("/api/apply/applications", json={"job_id": ashby_job.id}, headers=h).json()
    assert r["status"] == "ready_for_review"
    assert client.post(f"/api/apply/applications/{r['id']}/approve", headers=h).json()["status"] == "approved"


def test_nightly_matching_only_enabled_users(db, paid, free, monkeypatch):
    from tasks import apply_tasks
    monkeypatch.setattr(apply_tasks, "get_db", session_factory(db))
    make_job(db, ASHBY_URL, title="Enterprise Account Executive", company="Anyscale")
    pref = db.query(ApplyPreference).filter_by(user_id=paid.id).one()
    pref.enabled = True
    db.commit()
    assert apply_tasks.nightly_matching.run() == {"users": 1, "refreshed": 1}
    assert db.query(ApplyQueueItem).filter_by(user_id=paid.id).count() == 1


# =========================================================================== profile, readiness, answer bank

def test_profile_roundtrip_and_readiness(client, db, free):
    h = headers(free)
    prof = client.get("/api/apply/profile", headers=h).json()
    assert prof["first_name"] == "Ada" and prof["work_authorized_us"] is True and prof["requires_sponsorship"] is False
    assert prof["location"] == {"city": "New York", "state": "NY", "country": "United States"}
    assert prof["eeo"]["opt_in"] is False
    r = client.put("/api/apply/profile", headers=h, json={
        "phone": "", "earliest_start_date": "2026-11-01", "salary_expectation": "$150k",
        "eeo": {"opt_in": True, "gender": "Female"}, "location": {"city": "Boston"}, "email": "jobs@ada.dev"})
    body = r.json()
    assert body["phone"] is None and body["earliest_start_date"] == "2026-11-01"
    assert body["eeo"] == {"opt_in": True, "gender": "Female", "race": None, "veteran": None, "disability": None}
    assert body["location"]["city"] == "Boston" and body["location"]["state"] == "NY"
    assert body["email"] == "jobs@ada.dev"
    db.refresh(free)
    assert free.email == "free@example.com"  # login email untouched
    assert client.put("/api/apply/profile", headers=h, json={"earliest_start_date": "soon"}).status_code == 422
    ready = client.get("/api/apply/readiness", headers=h).json()
    assert ready == {"ready": False, "plan_ok": False, "resume_ok": True,
                     "missing": [{"field": "phone", "label": "Phone"}]}


def test_answer_bank_crud_and_save_to_bank(client, db, paid, gh_job):
    h = headers(paid)
    created = client.post("/api/apply/answer-bank", headers=h,
                          json={"label": "How did you hear about us?", "value": "LinkedIn"})
    assert created.status_code == 201 and created.json()["question_key"] == "how did you hear about us"
    entry_id = created.json()["id"]
    upd = client.put(f"/api/apply/answer-bank/{entry_id}", headers=h, json={"value": "A friend", "sensitive": True})
    assert upd.json()["value"] == "A friend" and upd.json()["sensitive"] is True

    app = client.post("/api/apply/applications", json={"job_id": gh_job.id}, headers=h).json()
    client.patch(f"/api/apply/applications/{app['id']}/answers", headers=h, json={
        "answers": {"question_9019066008": "No", "question_18374300008": "I understand"}, "save_to_bank": True})
    keys = {row["question_key"] for row in client.get("/api/apply/answer-bank", headers=h).json()["items"]}
    assert "have you ever interviewed at anthropic before" in keys
    assert "agreement to arbitrate" not in keys  # attestations are never banked

    assert client.delete(f"/api/apply/answer-bank/{entry_id}", headers=h).json() == {"deleted": True, "id": entry_id}
    assert client.delete(f"/api/apply/answer-bank/{entry_id}", headers=h).status_code == 404


# =========================================================================== P0 hygiene

def test_legacy_auto_apply_router_is_gone(client, paid):
    h = headers(paid)
    assert client.post("/api/auto-apply/submit/1", headers=h).status_code == 404
    assert client.get("/api/auto-apply/preflight/1", headers=h).status_code == 404
    from main import app
    assert not [r.path for r in app.routes if getattr(r, "path", "").startswith("/api/auto-apply")]


def test_legacy_auto_apply_flag_defaults_off(db):
    from services import app_settings
    assert app_settings.schedule_settings(db)["auto_apply_enabled"] is False


def test_encryption_fails_closed_without_key(monkeypatch):
    from services import encryption
    monkeypatch.delenv("ENCRYPTION_KEY", raising=False)
    with pytest.raises(encryption.EncryptionNotConfigured):
        encryption.encrypt_value("secret")
    with pytest.raises(encryption.EncryptionNotConfigured):
        encryption.decrypt_value("gAAAA-anything")
    monkeypatch.setenv("ENCRYPTION_KEY", "short")
    with pytest.raises(encryption.EncryptionNotConfigured):
        encryption.encrypt_value("secret")
    monkeypatch.setenv("ENCRYPTION_KEY", "a-long-enough-test-encryption-key")
    assert encryption.decrypt_value(encryption.encrypt_value("secret")) == "secret"


def test_headless_submitters_removed():
    # The old headless submitters (incl. Workday account creation) are gone for good.
    assert not list((Path(__file__).resolve().parents[1] / "services" / "auto_apply").glob("*.py"))
