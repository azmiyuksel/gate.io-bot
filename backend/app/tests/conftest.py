import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  ensure all entities are registered on Base.metadata
from app.core.config import Settings
from app.core.security import create_access_token
from app.db.session import Base
from app.models.entities import User
from app.models.enums import UserRole


@pytest.fixture()
def db_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def settings(monkeypatch):
    """Provide a test-friendly Settings instance with safe defaults."""
    s = Settings(
        environment="local",
        secret_key="test-secret-key-for-unit-tests",
        fernet_key="test-fernet-key",
        bot_enabled=False,
        gateio_api_key="",
        gateio_api_secret="",
        telegram_bot_token="",
        telegram_chat_id="",
    )
    monkeypatch.setattr("app.core.config.get_settings", lambda: s)
    return s


@pytest.fixture()
def test_user(db_session):
    """Create and return a test user in the database."""
    user = User(
        email="test@example.com",
        password_hash="not-a-real-hash",
        role=UserRole.admin,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def auth_headers(test_user):
    """Return Authorization headers with a valid JWT for the test user."""
    token = create_access_token(str(test_user.id), test_user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def fake_redis():
    """In-memory Redis mock for testing cached functions."""

    class FakeRedis:
        def __init__(self):
            self._store: dict[str, str] = {}

        def get(self, key: str) -> str | None:
            return self._store.get(key)

        def set(self, key: str, value: str, **kwargs) -> bool:
            self._store[key] = value
            return True

        def setex(self, key: str, _ttl: int, value: str) -> bool:
            self._store[key] = value
            return True

        def delete(self, *keys: str) -> int:
            count = 0
            for k in keys:
                if k in self._store:
                    del self._store[k]
                    count += 1
            return count

        def exists(self, key: str) -> bool:
            return key in self._store

        def ping(self) -> bool:
            return True

    return FakeRedis()
