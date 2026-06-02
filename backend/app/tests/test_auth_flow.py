"""End-to-end tests for the hardened auth layer and route consolidation."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  register entities on Base.metadata
from app.api.v1 import auth as auth_module
from app.core.security import hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models.entities import User
from app.models.enums import UserRole


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    # Seed an admin user.
    seed = TestingSession()
    seed.add(
        User(email="admin@example.com", password_hash=hash_password("secret123"), role=UserRole.admin)
    )
    seed.commit()
    seed.close()

    # Reset the in-process login throttle between tests.
    auth_module._login_limiter._hits.clear()

    # Construct without the context-manager form so the app lifespan (which would
    # call init_db against the real Postgres engine) does not run.
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_login_returns_access_and_refresh(client):
    res = client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "secret123"})
    assert res.status_code == 200
    body = res.json()
    assert body["access_token"] and body["refresh_token"]


def test_refresh_rotates_and_revokes_old(client):
    login = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "secret123"}
    ).json()
    first_refresh = login["refresh_token"]

    res = client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert res.status_code == 200
    assert res.json()["access_token"]

    # The rotated (old) refresh token must no longer be accepted.
    reused = client.post("/api/v1/auth/refresh", json={"refresh_token": first_refresh})
    assert reused.status_code == 401


def test_logout_revokes_refresh_token(client):
    refresh = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "secret123"}
    ).json()["refresh_token"]

    assert client.post("/api/v1/auth/logout", json={"refresh_token": refresh}).status_code == 204
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": refresh}).status_code == 401


def test_access_token_protects_admin_routes(client):
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "secret123"}
    ).json()

    # No token -> 401.
    assert client.post("/api/v1/circuit-breaker/trip").status_code == 401

    # Refresh token cannot be used as an access token.
    bad = client.get(
        "/api/v1/dashboard/summary",
        headers={"Authorization": f"Bearer {tokens['refresh_token']}"},
    )
    assert bad.status_code == 401


def test_login_rate_limited_after_repeated_failures(client):
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": "admin@example.com", "password": "wrong"})
    blocked = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "wrong"}
    )
    assert blocked.status_code == 429


def test_legacy_unversioned_routes_are_gone(client):
    # Consolidation: only /api/v1 is served now.
    assert client.get("/api/dashboard/summary").status_code == 404
    assert client.get("/walkforward").status_code == 404
