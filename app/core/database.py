from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

engine = create_engine(
    settings.SQLALCHEMY_DATABASE_URI,
    pool_pre_ping=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
)
# expire_on_commit=False: objects stay readable after commit (e.g. when serializing responses)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """One session per request. Rolled back automatically if the request fails."""
    with SessionLocal() as db:
        try:
            yield db
        except Exception:
            db.rollback()
            raise


DbSession = Annotated[Session, Depends(get_db)]
