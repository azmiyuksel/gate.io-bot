from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


_settings = get_settings()
# SQLite (tests) does not support pool sizing args; only tune real pools.
_pool_kwargs: dict = {}
if not _settings.database_url.startswith("sqlite"):
    _pool_kwargs = {
        "pool_size": 10,
        "max_overflow": 10,
        "pool_recycle": 1800,  # recycle connections every 30m to avoid stale handles
        "pool_timeout": 30,
    }

engine = create_engine(_settings.database_url, pool_pre_ping=True, **_pool_kwargs)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
