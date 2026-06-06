from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test_refcheck_be2.db")
os.environ.setdefault("FILE_STORAGE_DIR", "./data/test_uploads")

import pytest  # noqa: E402

from app.db.init_db import drop_db_for_tests_only, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database() -> None:
    drop_db_for_tests_only()
    init_db()
    yield
