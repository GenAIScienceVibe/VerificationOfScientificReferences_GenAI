from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine: Engine = create_engine(settings.database_url, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_sqlite_parent_directory() -> None:
    if settings.database_url.startswith("sqlite"):
        raw_path = settings.database_url.replace("sqlite:///", "", 1)
        Path(raw_path).parent.mkdir(parents=True, exist_ok=True)


def get_db() -> Generator[Session, None, None]:
    ensure_sqlite_parent_directory()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database_ready() -> tuple[bool, str]:
    try:
        ensure_sqlite_parent_directory()
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True, "ready"
    except Exception as exc:  # pragma: no cover - failure path depends on environment
        return False, f"unavailable: {exc.__class__.__name__}"
