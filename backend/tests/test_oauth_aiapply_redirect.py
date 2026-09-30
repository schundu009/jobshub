"""Google sign-in can return to AIApply, and only to the configured AIApply URL."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.responses import RedirectResponse

from routes import oauth


def _configure_google(monkeypatch, captured):
    async def authorize_redirect(request, redirect_uri):
        captured["redirect_uri"] = redirect_uri
        return RedirectResponse("https://accounts.google.com/o/oauth2/v2/auth")

    monkeypatch.setattr(oauth.settings, "google_client_id", "client-id")
    monkeypatch.setattr(oauth.settings, "google_client_secret", "client-secret")
    monkeypatch.setattr(oauth.settings, "backend_url", "https://backend.test")
    monkeypatch.setattr(oauth, "oauth", SimpleNamespace(google=SimpleNamespace(
        authorize_redirect=authorize_redirect,
        authorize_access_token=AsyncMock(return_value={"userinfo": {
            "sub": "g-1", "email": "admin@example.com", "name": "Admin", "email_verified": True}}),
    )))


def test_aiapply_callback_url_uses_configured_origin(monkeypatch):
    monkeypatch.setattr(oauth.settings, "aiapply_url", "https://aiapply.example/")
    assert oauth.aiapply_callback_url() == "https://aiapply.example/auth/callback"



def test_google_login_accepts_aiapply_and_callback_redirects_there(client, db, monkeypatch):
    captured = {}
    _configure_google(monkeypatch, captured)
    monkeypatch.setattr(oauth.settings, "aiapply_url", "https://aiapply.example")

    start = client.get("/auth/google/login?redirect=aiapply", follow_redirects=False)
    assert start.status_code in (302, 307)
    # The Google -> backend callback URI is unchanged for every portal.
    assert captured["redirect_uri"] == "https://backend.test/auth/google/callback"

    done = client.get("/auth/google/callback", follow_redirects=False)
    url = urlsplit(done.headers["location"])
    assert (url.scheme, url.netloc, url.path) == ("https", "aiapply.example", "/auth/callback")
    fragment = parse_qs(url.fragment)
    assert fragment["access_token"] and fragment["refresh_token"]
    assert done.headers["cache-control"] == "no-store"


def test_google_failure_for_aiapply_returns_error_to_aiapply(client, monkeypatch):
    captured = {}
    _configure_google(monkeypatch, captured)
    monkeypatch.setattr(oauth.settings, "aiapply_url", "https://aiapply.example")
    oauth.oauth.google.authorize_access_token = AsyncMock(side_effect=ValueError("boom"))
    client.get("/auth/google/login?redirect=aiapply", follow_redirects=False)
    done = client.get("/auth/google/callback", follow_redirects=False)
    location = done.headers["location"]
    assert location.startswith("https://aiapply.example/auth/callback#")
    assert "error=oauth_failed" in location
    assert "access_token=" not in location


@pytest.mark.parametrize("target", [
    "https://evil.example", "https://aiapply.up.railway.app", "aiapply.evil", "AIAPPLY", "",
])
def test_unknown_redirect_targets_are_rejected(client, monkeypatch, target):
    _configure_google(monkeypatch, {})
    response = client.get("/auth/google/login", params={"redirect": target}, follow_redirects=False)
    assert response.status_code == 422



def test_aiapply_url_comes_from_env_with_production_default():
    import os
    assert oauth.settings.aiapply_url == os.environ.get("AIAPPLY_URL", "https://aiapply.up.railway.app")
