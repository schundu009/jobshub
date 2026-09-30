from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit, parse_qs
from datetime import datetime, timezone, timedelta

import pytest
from routes import oauth
from models import User


def google_stub(monkeypatch, info=None, error=None):
    authorize = AsyncMock(side_effect=error, return_value={'userinfo': info})
    monkeypatch.setattr(oauth, 'oauth', SimpleNamespace(google=SimpleNamespace(authorize_access_token=authorize)))
    return authorize


def test_provider_availability_does_not_expose_credentials(client, monkeypatch):
    monkeypatch.setattr(oauth.settings, 'google_client_id', 'client-id')
    monkeypatch.setattr(oauth.settings, 'google_client_secret', 'private-secret')
    response = client.get('/auth/providers')
    assert response.status_code == 200
    assert response.json()['google'] is True
    assert 'private-secret' not in response.text
    monkeypatch.setattr(oauth.settings, 'google_client_secret', '')
    assert client.get('/auth/providers').json()['google'] is False
    assert client.get('/auth/google/login', follow_redirects=False).status_code == 501


@pytest.mark.parametrize('info', [None, {'sub':'1'}, {'sub':'1','email':'user@example.com','email_verified':False}])
def test_google_requires_verified_email(client, db, monkeypatch, info):
    google_stub(monkeypatch, info)
    response = client.get('/auth/google/callback', follow_redirects=False)
    assert 'error=oauth_failed' in response.headers['location']
    assert db.query(User).count() == 0


def test_google_success_and_fragment_encoding(client, db, monkeypatch):
    google_stub(monkeypatch, {'sub':'123', 'email':'hello+jobs@example.com', 'name':'A & B 100%', 'email_verified':True})
    response = client.get('/auth/google/callback', follow_redirects=False)
    url = urlsplit(response.headers['location'])
    assert url.netloc == 'cariara.com' and url.path == '/jobs/admin/login.html'
    fragment = parse_qs(url.fragment)
    assert fragment['user_name'] == ['A & B 100%']
    assert fragment['user_email'] == ['hello+jobs@example.com']
    assert fragment['access_token']
    assert response.headers['cache-control'] == 'no-store'
    assert db.query(User).one().is_email_verified


@pytest.mark.parametrize('locked', [False, True])
def test_google_cannot_bypass_disabled_or_locked_account(client, db, users, monkeypatch, locked):
    user=users[0]
    if locked:
        user.locked_until=datetime.now(timezone.utc)+timedelta(minutes=15)
    else:
        user.is_active=False
    db.commit()
    db.expire_all()
    google_stub(monkeypatch, {'sub':'123','email':user.email,'email_verified':True})
    response=client.get('/auth/google/callback',follow_redirects=False)
    assert 'error=oauth_failed' in response.headers['location']
    assert 'access_token=' not in response.headers['location']


def test_google_state_failure_is_sanitized(client, monkeypatch):
    google_stub(monkeypatch, error=ValueError('sensitive-provider-details'))
    response=client.get('/auth/google/callback',follow_redirects=False)
    assert 'error=oauth_failed' in response.headers['location']
    assert 'sensitive-provider-details' not in response.headers['location']


def test_google_rejects_arbitrary_redirect_portal(client):
    assert client.get('/auth/google/login?redirect=https://evil.example').status_code == 422


def test_google_authorization_uses_state_and_rejects_mismatch(client, monkeypatch):
    from authlib.integrations.starlette_client import OAuth
    registry=OAuth()
    registry.register(name='google',client_id='test-client',client_secret='test-secret',
                      authorize_url='https://accounts.google.com/o/oauth2/v2/auth',
                      access_token_url='https://oauth2.googleapis.com/token',
                      client_kwargs={'scope':'openid email profile'})
    monkeypatch.setattr(oauth,'oauth',registry)
    monkeypatch.setattr(oauth.settings,'google_client_id','test-client')
    monkeypatch.setattr(oauth.settings,'google_client_secret','test-secret')
    monkeypatch.setattr(oauth.settings,'backend_url','http://localhost:8000')
    response=client.get('/auth/google/login?redirect=admin',follow_redirects=False)
    assert response.status_code in (302,307)
    params=parse_qs(urlsplit(response.headers['location']).query)
    assert params['state'][0]
    assert params['nonce'][0]
    assert params['redirect_uri']==['http://localhost:8000/auth/google/callback']
    assert set(params['scope'][0].split())=={'openid','email','profile'}
    response=client.get('/auth/google/callback?code=fake-code&state=wrong',follow_redirects=False)
    assert 'error=oauth_failed' in response.headers['location']
    assert 'access_token=' not in response.headers['location']
