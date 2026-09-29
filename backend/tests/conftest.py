"""Isolated test configuration: never connect to the configured application DB."""
import os
import sys
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["SKIP_EARLY_MIGRATIONS"] = "1"
os.environ["SKIP_MIGRATIONS"] = "1"
os.environ["SECRET_KEY"] = "isolated-test-signing-key-not-for-production"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from main import app
from models import User
from services.redis_service import redis_service
from utils.security import hash_password


@pytest.fixture
def db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


@pytest.fixture
def users(db):
    rows = [User(email=f"user{i}@example.com", name=f"User {i}",
                 password_hash=hash_password("Test-password-123"), is_active=True)
            for i in range(2)]
    db.add_all(rows)
    db.commit()
    return rows


@pytest.fixture
def client(db, monkeypatch):
    def override_db():
        yield db
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr(redis_service, "ping", lambda: False)
    # Keep tests off any real Redis: open the service's circuit breaker so
    # cache/rate-limit calls fail open without network I/O.
    monkeypatch.setattr(redis_service, "_down_until", float("inf"))
    monkeypatch.setattr(redis_service, "is_token_blacklisted", lambda _: False)
    monkeypatch.setattr(redis_service, "get_user_blacklist_time", lambda _: None)
    import main
    main.rate_limiter._fallback_requests.clear()
    monkeypatch.setattr(main, "API_KEY", "")
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
