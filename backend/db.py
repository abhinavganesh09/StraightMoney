"""
db.py — SQLAlchemy engine, session factory, base class, and FastAPI dependency.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from config import settings

engine = create_engine(
    settings.database_url,
    connect_args={"connect_timeout": 5} if settings.database_url.startswith("postgresql") else {},
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a DB session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all PostgreSQL tables at startup."""
    # Import models so SQLAlchemy picks up all mapped classes before create_all
    import models  # noqa: F401

    Base.metadata.create_all(bind=engine)

