"""Regression tests for job visibility, AI job endpoints, settings and error handling."""
import pytest
from fastapi.testclient import TestClient

import main
from models import Job, UserDocument
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
