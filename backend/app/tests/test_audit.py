"""Audit-trail tests: privileged actions are recorded with the acting user."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  register entities on Base.metadata
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

    seed = TestingSession()
    seed.add(
        User(email="admin@example.com", password_hash=hash_password("secret123"), role=UserRole.admin)
    )
    seed.commit()
    seed.close()

    yield TestClient(app)
    app.dependency_overrides.clear()


def _auth_header(client: TestClient) -> dict:
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "admin@example.com", "password": "secret123"}
    ).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_circuit_breaker_trip_is_audited(client):
    headers = _auth_header(client)

    res = client.post("/api/v1/circuit-breaker/trip", json={"reason": "test halt"}, headers=headers)
    assert res.status_code == 200

    audit = client.get("/api/v1/dashboard/audit", headers=headers)
    assert audit.status_code == 200
    entries = audit.json()
    assert any(
        e["action"] == "circuit_breaker.trip"
        and e["actor"] == "admin@example.com"
        and e["detail"] == "test halt"
        for e in entries
    )


def test_audit_endpoint_requires_admin(client):
    # A viewer token must not be able to read the audit log.
    seed_db = next(app.dependency_overrides[get_db]())
    seed_db.add(
        User(email="viewer@example.com", password_hash=hash_password("secret123"), role=UserRole.viewer)
    )
    seed_db.commit()
    tokens = client.post(
        "/api/v1/auth/login", json={"email": "viewer@example.com", "password": "secret123"}
    ).json()
    res = client.get(
        "/api/v1/dashboard/audit", headers={"Authorization": f"Bearer {tokens['access_token']}"}
    )
    assert res.status_code == 403
