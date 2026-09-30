import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

import main
from migrations.document_ownership import migrate_document_ownership
from models import Document, Job
from utils.security import as_utc, create_access_token


def headers(user):
    token, _ = create_access_token(user.id, user.email)
    return {"Authorization": f"Bearer {token}"}


def test_job_documents_require_document_owner(client, users, db):
    owner, stranger = users
    job = Job(title="Example", user_id=owner.id)
    db.add(job)
    db.flush()
    db.add_all([Document(name="Owned", job_id=job.id, user_id=owner.id),
                Document(name="Unowned", job_id=job.id)])
    db.commit()
    detail = client.get(f'/api/jobs/{job.id}', headers=headers(owner))
    assert [doc['name'] for doc in detail.json()['documents']] == ['Owned']


def test_ownership_migration_preserves_existing_and_quarantines_unknown():
    engine = create_engine('sqlite://')
    with engine.begin() as connection:
        connection.execute(text('CREATE TABLE users (id INTEGER PRIMARY KEY)'))
        connection.execute(text('CREATE TABLE jobs (id INTEGER PRIMARY KEY, user_id INTEGER)'))
        connection.execute(text('CREATE TABLE documents (id INTEGER PRIMARY KEY, job_id INTEGER)'))
        connection.execute(text('INSERT INTO users VALUES (7), (8)'))
        connection.execute(text('INSERT INTO jobs VALUES (1, 7), (2, NULL)'))
        connection.execute(text('INSERT INTO documents VALUES (1, 1), (2, NULL), (3, 2)'))
        migrate_document_ownership(connection)
        assert connection.execute(text('SELECT user_id FROM documents ORDER BY id')).scalars().all() == [7, None, None]
        connection.execute(text('UPDATE documents SET user_id=8 WHERE id=1'))
        migrate_document_ownership(connection)
        assert connection.execute(text('SELECT user_id FROM documents WHERE id=1')).scalar() == 8
    engine.dispose()


def test_api_key_exemptions_are_exact(monkeypatch):
    monkeypatch.setattr(main, 'API_KEY', 'required-test-key')
    app = FastAPI()
    app.add_middleware(main.APIKeyAuthMiddleware)
    @app.post('/api/write')
    @app.post('/auth/login')
    @app.post('/auth/login/extra')
    @app.post('/static-impostor')
    def endpoint():
        return {'ok': True}
    with TestClient(app) as client:
        assert client.post('/api/write').status_code == 401
        assert client.post('/api/write', headers={'X-API-Key': 'wrong'}).status_code == 401
        assert client.post('/api/write', headers={'X-API-Key': 'required-test-key'}).status_code == 200
        assert client.post('/auth/login').status_code == 200
        assert client.post('/auth/login/extra').status_code == 401
        assert client.post('/static-impostor').status_code == 401


def test_forged_tokens_cannot_rotate_login_buckets(monkeypatch):
    limiter = main.RateLimiter()
    monkeypatch.setattr(limiter, '_check_redis', lambda: False)
    monkeypatch.setattr(main, 'rate_limiter', limiter)
    app = FastAPI()
    app.add_middleware(main.RateLimitMiddleware)
    @app.post('/auth/login')
    def endpoint():
        return {'ok': True}
    with TestClient(app) as client:
        for i in range(11):
            payload = base64.urlsafe_b64encode(json.dumps({'sub': str(i)}).encode()).decode().rstrip('=')
            response = client.post('/auth/login', headers={'Authorization': f'Bearer x.{payload}.invalid'})
            assert response.status_code == (200 if i < 10 else 429)


def test_rate_limiter_fallback_categories_are_independent(monkeypatch):
    limiter = main.RateLimiter()
    monkeypatch.setattr(limiter, '_check_redis', lambda: False)
    for _ in range(10):
        assert limiter.is_allowed('same-client', 'api_read')[0]
    assert limiter.is_allowed('same-client', 'auth_login')[0]
    assert limiter.get_remaining('same-client', 'auth_login') == 9


@pytest.mark.parametrize('expired', [False, True])
def test_lockout_after_database_roundtrip(client, users, db, expired):
    user = users[0]
    user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=-1 if expired else 15)
    db.commit()
    db.expire_all()
    assert user.locked_until.tzinfo is None
    auth_headers = headers(user)
    response = client.get('/api/users/documents', headers=auth_headers)
    assert response.status_code == (200 if expired else 401)
    response = client.post('/auth/login', json={'email': user.email, 'password': 'Test-password-123'})
    assert response.status_code == (200 if expired else 401)
    if expired:
        db.refresh(user)
        assert user.locked_until is None
    else:
        assert 'locked' in response.json()['detail']


def test_aware_and_naive_timestamps_normalize_to_utc():
    assert as_utc(datetime(2026, 1, 1)) == datetime(2026, 1, 1, tzinfo=timezone.utc)
    aware = datetime(2026, 1, 1, 2, tzinfo=timezone(timedelta(hours=2)))
    assert as_utc(aware) == datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_only_verified_access_tokens_choose_user_buckets(monkeypatch):
    buckets = []
    class RecordingLimiter:
        def is_allowed(self, client_id, category):
            buckets.append(client_id)
            return True, 100, 0
    monkeypatch.setattr(main, 'rate_limiter', RecordingLimiter())
    app = FastAPI()
    app.add_middleware(main.RateLimitMiddleware)
    @app.get('/api/example')
    def endpoint():
        return {'ok': True}
    valid, _ = create_access_token(42, 'user@example.com')
    forged = valid.rsplit('.', 1)[0] + '.invalid'
    from utils.security import create_refresh_token
    refresh, _ = create_refresh_token(42)
    with TestClient(app) as client:
        for token in (forged, refresh, valid):
            assert client.get('/api/example', headers={'Authorization': f'Bearer {token}'}).status_code == 200
    assert buckets == ['testclient', 'testclient', 'user:42']


def test_failed_login_lockout_can_be_read_on_next_request(client, users, db):
    user = users[0]
    for _ in range(5):
        response = client.post('/auth/login', json={'email': user.email, 'password': 'wrong-password'})
        assert response.status_code == 401
        db.expire_all()
    assert user.locked_until is not None
    response = client.post('/auth/login', json={'email': user.email, 'password': 'Test-password-123'})
    assert response.status_code == 401
    assert 'locked' in response.json()['detail']
