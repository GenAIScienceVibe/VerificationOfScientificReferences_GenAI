from __future__ import annotations

from sqlalchemy import inspect

from app.db.base import Base
from app.db.session import engine, ensure_sqlite_parent_directory


def init_db() -> None:
    """Create all BE-2 tables for the local/demo database.

    This project intentionally does not introduce Alembic yet. For BE-2 local
    and demo use, table creation is handled through SQLAlchemy metadata.
    Alembic migrations can be added in a later hardening phase without changing
    model names or table names.
    """
    ensure_sqlite_parent_directory()
    import app.models  # noqa: F401 - registers SQLAlchemy models on Base.metadata

    Base.metadata.create_all(bind=engine)
    _apply_column_migrations()


def _apply_column_migrations() -> None:
    """Add new columns to existing tables without Alembic."""
    from sqlalchemy import text
    migrations = [
        ("claims", "preceding_context", "TEXT"),
    ]
    with engine.connect() as conn:
        for table, column, col_type in migrations:
            existing = [row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))]
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
                conn.commit()


def drop_db_for_tests_only() -> None:
    ensure_sqlite_parent_directory()
    import app.models  # noqa: F401

    Base.metadata.drop_all(bind=engine)


def list_table_names() -> list[str]:
    ensure_sqlite_parent_directory()
    return sorted(inspect(engine).get_table_names())
