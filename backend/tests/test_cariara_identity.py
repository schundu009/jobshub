"""cariara.com tokens on the jobportal API (services/cariara_identity.py), copilot mocked."""
import time
from datetime import datetime, timedelta

import httpx
import pytest
from jose import jwt

from models import Application, ApplyPreference, User
from services import cariara_identity as ci
from services.apply import plans
from utils.security import create_access_token

COPILOT_SECRET = "copilot-only-secret-jobportal-never-sees"


def cariara_token(email, sub="42", exp_in=3600, **extra):
    claims = {"sub": sub, "email": email, "name": "Cara User", "picture": "", "type": "access", "gen": 1,
              "exp": int(time.time()) + exp_in, **extra}
    return jwt.encode(claims, COPILOT_SECRET, algorithm="HS256")


class FakeCopilot:
    """Stands in for copilot-prep's /api/v1/auth/me and /api/v1/billing/subscription."""

    def __init__(self):
        self.accounts = {}  # token -> dict(user=..., plan=..., status=...)
        self.calls = {"me": 0, "subscription": 0}
        self.down = False

    def add(self, token, email, plan="free", status="active", is_admin=False, user_id="42"):
        self.accounts[token] = {"user": {"id": user_id, "email": email, "name": "Cara User", "is_admin": is_admin},
                                "plan": plan, "status": status}
        return token

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.down:
            raise httpx.ConnectTimeout("copilot down", request=request)
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        account = self.accounts.get(token)
        if request.url.path == "/api/v1/auth/me":
            self.calls["me"] += 1
            if not account:
                return httpx.Response(401, json={"error": "Invalid or expired token"})
            return httpx.Response(200, json={"authenticated": True, "access_token": token, "user": account["user"]})
        if request.url.path == "/api/v1/billing/subscription":
            self.calls["subscription"] += 1
            if not account:
                return httpx.Response(401, json={"error": "Invalid or expired token"})
            return httpx.Response(200, json={"plan": account["plan"], "plan_type": account["plan"],
                                             "status": account["status"]})
        return httpx.Response(404)


@pytest.fixture
def copilot(monkeypatch):
    fake = FakeCopilot()
    real_client = httpx.Client

    def client_factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(fake.handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(ci.httpx, "Client", client_factory)
    monkeypatch.setattr(ci.settings, "cariara_auth_enabled", True)
    # Never touch a real Redis: open its circuit so the in-process cache is used.
    monkeypatch.setattr(ci.redis_service, "_down_until", float("inf"))
    monkeypatch.setattr(plans, "verify_subscription_sync", lambda user_id: {"hasAccess": False, "planType": "free"})
    ci.clear_local_cache()
    yield fake
    ci.clear_local_cache()


def bearer(token):
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- identity

def test_valid_token_creates_linked_user(client, db, copilot):
    token = copilot.add(cariara_token("New.Person@Example.com"), "New.Person@Example.com", user_id="77")

    r = client.get("/api/users/me", headers=bearer(token))

    assert r.status_code == 200, r.text
    user = db.query(User).filter(User.email == "new.person@example.com").one()
    assert user.cariara_user_id == "77"
    assert user.identity_source == "cariara"
    assert user.role == "user"
    assert user.is_email_verified
    assert user.password_hash is None


def test_existing_user_is_linked_by_email_not_duplicated(client, db, users, copilot):
    token = copilot.add(cariara_token("USER0@example.com"), "USER0@example.com", user_id="9")

    r = client.get("/auth/cariara/whoami", headers=bearer(token))

    assert r.status_code == 200, r.text
    assert r.json()["jobportal_user_id"] == users[0].id
    assert db.query(User).count() == 2
    db.refresh(users[0])
    assert users[0].cariara_user_id == "9"
    assert users[0].identity_source is None  # native account keeps its source


def test_second_call_uses_cache(client, copilot):
    token = copilot.add(cariara_token("cache@example.com"), "cache@example.com")

    assert client.get("/api/users/me", headers=bearer(token)).status_code == 200
    assert client.get("/api/users/me", headers=bearer(token)).status_code == 200

    assert copilot.calls == {"me": 1, "subscription": 1}


def test_cache_key_is_token_hash(copilot):
    token = copilot.add(cariara_token("hash@example.com"), "hash@example.com")
    ci.verify_cariara_token(token)
    key = next(iter(ci._local_cache))
    assert token not in key and key.startswith(ci.CACHE_PREFIX) and len(key) == len(ci.CACHE_PREFIX) + 64


def test_invalid_token_is_401_and_negative_cached(client, copilot):
    token = cariara_token("nobody@example.com")  # copilot doesn't know it

    assert client.get("/api/users/me", headers=bearer(token)).status_code == 401
    assert client.get("/api/users/me", headers=bearer(token)).status_code == 401
    assert copilot.calls["me"] == 1


def test_expired_token_is_401_without_network(client, copilot):
    token = copilot.add(cariara_token("old@example.com", exp_in=-10), "old@example.com")

    r = client.get("/api/users/me", headers=bearer(token))

    assert r.status_code == 401
    assert copilot.calls["me"] == 0


def test_garbage_token_is_401_without_network(client, copilot):
    assert client.get("/api/users/me", headers=bearer("not-a-jwt")).status_code == 401
    assert copilot.calls["me"] == 0


def test_forged_jobportal_shaped_token_is_not_forwarded(client, users, copilot):
    forged = jwt.encode({"sub": str(users[0].id), "email": users[0].email, "role": "admin", "type": "access",
                         "jti": "x", "exp": int(time.time()) + 600}, "wrong-key", algorithm="HS256")

    assert client.get("/api/users/me", headers=bearer(forged)).status_code == 401
    assert copilot.calls["me"] == 0


def test_copilot_down_fails_closed_with_503_and_is_not_cached(client, copilot):
    token = copilot.add(cariara_token("down@example.com"), "down@example.com")
    copilot.down = True

    assert client.get("/api/users/me", headers=bearer(token)).status_code == 503

    copilot.down = False
    assert client.get("/api/users/me", headers=bearer(token)).status_code == 200


def test_optional_auth_returns_none_when_copilot_down(db, copilot):
    from fastapi.security import HTTPAuthorizationCredentials
    from middleware.auth import get_current_user_optional

    token = copilot.add(cariara_token("opt@example.com"), "opt@example.com")
    copilot.down = True
    creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
    assert get_current_user_optional(creds, db) is None


def test_x_cariara_token_header(client, copilot):
    token = copilot.add(cariara_token("hdr@example.com"), "hdr@example.com")

    r = client.get("/api/users/me", headers={"X-Cariara-Token": token})

    assert r.status_code == 200, r.text


def test_disabled_account_is_rejected(client, db, users, copilot):
    users[1].is_active = False
    db.commit()
    token = copilot.add(cariara_token(users[1].email), users[1].email)

    assert client.get("/api/users/me", headers=bearer(token)).status_code == 401


def test_cariara_auth_can_be_switched_off(client, copilot, monkeypatch):
    monkeypatch.setattr(ci.settings, "cariara_auth_enabled", False)
    token = copilot.add(cariara_token("off@example.com"), "off@example.com")

    assert client.get("/api/users/me", headers=bearer(token)).status_code == 401
    assert copilot.calls["me"] == 0


# --------------------------------------------------------------------------- jobportal tokens unchanged

def test_jobportal_token_still_works_without_copilot(client, users, copilot):
    token, _ = create_access_token(users[0].id, users[0].email)

    r = client.get("/api/users/me", headers=bearer(token))

    assert r.status_code == 200, r.text
    assert copilot.calls["me"] == 0


def test_whoami_rejects_jobportal_token(client, users, copilot):
    token, _ = create_access_token(users[0].id, users[0].email)
    assert client.get("/auth/cariara/whoami", headers=bearer(token)).status_code == 400


def test_whoami_requires_a_token(client, copilot):
    assert client.get("/auth/cariara/whoami").status_code == 401


# --------------------------------------------------------------------------- plan mapping

def _approved_application(db, user):
    from models import Company, Job
    company = Company(name="Acme")
    db.add(company)
    db.flush()
    job = Job(title="Engineer", company_id=company.id, job_url="https://boards.greenhouse.io/acme/jobs/1",
              is_active=True)
    db.add(job)
    db.flush()
    app = Application(user_id=user.id, job_id=job.id, status="approved")
    db.add(app)
    db.commit()
    return app


@pytest.mark.parametrize("plan", ["platform", "byok", "lifetime", "team"])
def test_paid_cariara_plan_passes_auto_apply_gate(client, db, copilot, plan):
    token = copilot.add(cariara_token(f"{plan}@example.com"), f"{plan}@example.com", plan=plan)
    assert client.get("/api/apply/preferences", headers=bearer(token)).json()["plan_ok"] is True
    user = db.query(User).filter(User.email == f"{plan}@example.com").one()
    app = _approved_application(db, user)

    r = client.post(f"/api/apply/applications/{app.id}/approve", headers=bearer(token))

    assert r.status_code == 200, r.text
    whoami = client.get("/auth/cariara/whoami", headers=bearer(token)).json()
    assert whoami["plan"] == plan and whoami["plan_ok"] is True


@pytest.mark.parametrize("plan,status", [("free", "active"), ("platform", "past_due"), ("platform", "canceled")])
def test_unpaid_cariara_plan_gets_402(client, db, copilot, plan, status):
    email = f"free-{plan}-{status}@example.com"
    token = copilot.add(cariara_token(email), email, plan=plan, status=status)
    client.get("/api/users/me", headers=bearer(token))
    user = db.query(User).filter(User.email == email).one()
    app = _approved_application(db, user)

    r = client.post(f"/api/apply/applications/{app.id}/approve", headers=bearer(token))

    assert r.status_code == 402
    assert client.get("/auth/cariara/whoami", headers=bearer(token)).json()["plan_ok"] is False


def test_stored_cariara_plan_used_without_token_then_expires(db, copilot, monkeypatch):
    user = User(email="bg@example.com", name="Bg", is_active=True, cariara_plan="platform",
                cariara_plan_checked_at=ci._utcnow() - timedelta(hours=1))
    db.add(user)
    db.commit()
    assert plans.resolve_plan(user).plan_ok  # e.g. a Celery task, no request token

    user.cariara_plan_checked_at = ci._utcnow() - timedelta(hours=ci.settings.cariara_plan_max_age_hours + 1)
    assert not plans.resolve_plan(user).plan_ok


def test_cariara_plan_is_stored_on_user(client, db, copilot):
    token = copilot.add(cariara_token("store@example.com"), "store@example.com", plan="byok")
    client.get("/api/users/me", headers=bearer(token))
    user = db.query(User).filter(User.email == "store@example.com").one()
    assert user.cariara_plan == "byok" and user.cariara_plan_checked_at is not None


def test_free_override_still_wins_over_cariara_plan(client, db, copilot):
    token = copilot.add(cariara_token("ovr@example.com"), "ovr@example.com", plan="platform")
    client.get("/api/users/me", headers=bearer(token))
    user = db.query(User).filter(User.email == "ovr@example.com").one()
    db.add(ApplyPreference(user_id=user.id, plan_override="free"))
    db.commit()

    assert client.get("/api/apply/preferences", headers=bearer(token)).json()["plan_ok"] is False


# --------------------------------------------------------------------------- admin mapping

def test_cariara_admin_is_not_jobportal_admin(client, db, copilot):
    token = copilot.add(cariara_token("cadmin@example.com"), "cadmin@example.com", is_admin=True)

    body = client.get("/auth/cariara/whoami", headers=bearer(token)).json()

    assert body["cariara_admin"] is True and body["is_admin"] is False
    assert client.get("/api/users", headers=bearer(token)).status_code == 403
    assert db.query(User).filter(User.email == "cadmin@example.com").one().role == "user"


def test_existing_jobportal_admin_keeps_admin_via_cariara_token(client, db, users, copilot):
    users[0].role = "admin"
    db.commit()
    token = copilot.add(cariara_token(users[0].email), users[0].email, is_admin=False)

    assert client.get("/auth/cariara/whoami", headers=bearer(token)).json()["is_admin"] is True
    assert client.get("/api/users", headers=bearer(token)).status_code == 200
    db.refresh(users[0])
    assert users[0].role == "admin"


# --------------------------------------------------------------------------- CORS

@pytest.mark.parametrize("origin", ["https://cariara.com", "https://www.cariara.com"])
@pytest.mark.parametrize("path", ["/api/apply/preferences", "/api/users/documents", "/api/users/settings",
                                  "/api/jobs"])
def test_cors_preflight_from_cariara(client, origin, path):
    r = client.options(path, headers={
        "Origin": origin,
        "Access-Control-Request-Method": "GET",
        "Access-Control-Request-Headers": "authorization,x-cariara-token,content-type",
    })

    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == origin
    allowed = r.headers["access-control-allow-headers"].lower()
    assert "authorization" in allowed and "x-cariara-token" in allowed


def test_cors_preflight_rejects_unknown_origin(client):
    r = client.options("/api/apply/preferences", headers={
        "Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert r.headers.get("access-control-allow-origin") != "https://evil.example"


# --------------------------------------------------------------------------- migration

def test_migration_adds_columns_idempotently():
    from sqlalchemy import create_engine, inspect, text

    from migrations.cariara_identity import CARIARA_USER_ID_INDEX, migrate_cariara_identity

    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, email VARCHAR(255))"))
        assert set(migrate_cariara_identity(conn)) == {
            "cariara_user_id", "identity_source", "cariara_plan", "cariara_plan_checked_at"}
        assert migrate_cariara_identity(conn) == []
        indexes = {ix["name"]: ix for ix in inspect(conn).get_indexes("users")}
        assert indexes[CARIARA_USER_ID_INDEX]["unique"]
