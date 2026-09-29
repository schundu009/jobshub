"""Regression tests for job visibility, AI job endpoints, settings and error handling."""
import pytest
from fastapi.testclient import TestClient

import main
from models import Job, User, UserDocument
from routes import ai as ai_routes
from routes import jobs as jobs_routes
from utils.security import create_access_token


def headers(user):
    token, _ = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


RESUME = "Jane Doe\nSenior Engineer\n" + "Built distributed systems in Python. " * 5


@pytest.fixture
def jobs_setup(db, users):
    owner, stranger = users
    shared = Job(title="Shared SRE", is_active=True,
                 job_description="<p>Hello &amp; welcome</p><ul><li>Python</li><li>Go</li></ul>" + "<p>x</p>" * 300)
    private = Job(title="Private tracked", is_active=True, user_id=owner.id, job_description="<p>mine</p>")
    db.add_all([shared, private])
    db.add(UserDocument(user_id=owner.id, filename="r.txt", document_type="resume",
                        is_default=True, content_text=RESUME, file_path=None))
    db.commit()
    return shared, private


def test_job_list_hides_other_users_private_jobs(client, users, jobs_setup):
    owner, stranger = users
    shared, private = jobs_setup
    ids = lambda r: {j["id"] for j in r.json()["jobs"]}
    assert ids(client.get("/api/jobs?all=true", headers=headers(owner))) == {shared.id, private.id}
    assert ids(client.get("/api/jobs?all=true", headers=headers(stranger))) == {shared.id}
    assert ids(client.get("/api/jobs?all=true")) == {shared.id}


def test_description_chars_returns_truncated_plain_text(client, users, jobs_setup):
    shared, _ = jobs_setup
    full = client.get("/api/jobs?all=true").json()["jobs"]
    assert "<p>" in next(j for j in full if j["id"] == shared.id)["job_description"]
    short = client.get("/api/jobs?all=true&description_chars=100").json()["jobs"]
    desc = next(j for j in short if j["id"] == shared.id)["job_description"]
    assert "<" not in desc and desc.startswith("Hello & welcome Python Go")
    assert len(desc) <= 100
    assert client.get("/api/jobs?all=true&description_chars=5").status_code == 422


def test_ai_summary_requires_auth_and_ignores_force_for_non_admin(client, users, jobs_setup, monkeypatch):
    owner, _ = users
    shared, _ = jobs_setup
    assert client.post(f"/api/jobs/{shared.id}/ai-summary").status_code in (401, 403)
    shared.ai_summary, shared.ai_tech_stack = "cached", ["python"]
    import services.ai_service as svc
    monkeypatch.setattr(svc, "summarize_job_description", lambda *a: pytest.fail("should use cache"))
    r = client.post(f"/api/jobs/{shared.id}/ai-summary?force=true", headers=headers(owner))
    assert r.status_code == 200 and r.json()["cached"] is True


def test_ai_summary_rate_limited(client, users, jobs_setup, monkeypatch):
    owner, _ = users
    shared, _ = jobs_setup
    import services.ai_service as svc
    monkeypatch.setattr(svc, "summarize_job_description", lambda *a: {"summary": "", "tech_tools": []})
    monkeypatch.setattr(jobs_routes, "AI_SUMMARY_RATE_LIMIT", 2)
    jobs_routes._ai_summary_calls.clear()
    codes = [client.post(f"/api/jobs/{shared.id}/ai-summary", headers=headers(owner)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    jobs_routes._ai_summary_calls.clear()


def test_tailor_endpoints_json_format_and_overrides(client, users, jobs_setup, monkeypatch):
    owner, stranger = users
    shared, private = jobs_setup
    seen = {}

    def fake_tailor(resume_text, job_title, job_description, company_name):
        seen["resume"], seen["jd"] = resume_text, job_description
        return "TAILORED RESUME"

    monkeypatch.setattr(ai_routes.ai_service, "generate_ats_tailored_resume", fake_tailor)
    monkeypatch.setattr(ai_routes.ai_service, "generate_cover_letter", lambda **kw: "Dear team")

    r = client.post(f"/api/ai/tailor-resume/{shared.id}?format=json", headers=headers(owner))
    assert r.status_code == 200 and r.json()["tailored_resume"] == "TAILORED RESUME"
    assert seen["resume"] == RESUME

    r = client.post(f"/api/ai/tailor-resume/{shared.id}?format=json", headers=headers(owner),
                    json={"resume_text": "edited resume", "job_description": "edited jd"})
    assert r.status_code == 200 and seen == {"resume": "edited resume", "jd": "edited jd"}

    r = client.post(f"/api/ai/generate-cover-letter/{shared.id}?format=json", headers=headers(owner))
    assert r.status_code == 200 and r.json()["cover_letter"] == "Dear team"

    # Default stays DOCX for existing callers
    r = client.post(f"/api/ai/tailor-resume/{shared.id}", headers=headers(owner))
    assert r.status_code == 200 and "wordprocessingml" in r.headers["content-type"]

    # Stranger without resume / private job
    assert client.post(f"/api/ai/tailor-resume/{shared.id}?format=json", headers=headers(stranger)).status_code == 400
    assert client.post(f"/api/ai/tailor-resume/{private.id}?format=json", headers=headers(stranger)).status_code == 403

    r = client.post("/api/ai/render-docx", headers=headers(owner),
                    json={"kind": "cover_letter", "text": "Dear team", "job_id": shared.id})
    assert r.status_code == 200 and r.content[:2] == b"PK"


def test_settings_cannot_change_email_and_persists_base_resume(client, users, db):
    owner, stranger = users
    doc = UserDocument(user_id=owner.id, filename="r.txt", document_type="resume", content_text=RESUME)
    other = UserDocument(user_id=stranger.id, filename="s.txt", document_type="resume", content_text=RESUME)
    db.add_all([doc, other])
    db.commit()
    r = client.put("/api/users/settings", headers=headers(owner),
                   json={"email": "HIJACK@example.com", "phone": "123", "base_resume_id": doc.id})
    assert r.status_code == 200
    db.refresh(owner)
    assert owner.email == "user0@example.com" and owner.phone == "123" and owner.base_resume_id == doc.id
    # Someone else's document id is ignored
    client.put("/api/users/settings", headers=headers(owner), json={"base_resume_id": other.id})
    db.refresh(owner)
    assert owner.base_resume_id == doc.id
    # Deleting a document with no file_path works and clears the base resume
    r = client.delete(f"/api/users/documents/{doc.id}", headers=headers(owner))
    assert r.status_code == 200
    db.refresh(owner)
    assert owner.base_resume_id is None


def test_unhandled_exception_returns_json_500_with_cors(client):
    origin = main.ALLOWED_ORIGINS[0]

    @main.app.get("/api/__boom_test")
    def boom():
        raise RuntimeError("boom")

    try:
        c = TestClient(main.app, raise_server_exceptions=False)
        r = c.get("/api/__boom_test", headers={"Origin": origin})
        assert r.status_code == 500
        assert r.json() == {"detail": "Internal server error"}
        assert r.headers.get("access-control-allow-origin") == origin
    finally:
        main.app.router.routes = [rt for rt in main.app.router.routes if getattr(rt, "path", "") != "/api/__boom_test"]
