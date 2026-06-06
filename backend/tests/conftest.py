from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test_refcheck_be3.db")
os.environ.setdefault("FILE_STORAGE_DIR", "./data/test_uploads_be3")
os.environ.setdefault("MAX_UPLOAD_SIZE_BYTES", str(2 * 1024 * 1024))

import pytest  # noqa: E402

from app.db.init_db import drop_db_for_tests_only, init_db  # noqa: E402


@pytest.fixture(autouse=True)
def reset_database_and_storage() -> None:
    drop_db_for_tests_only()
    init_db()
    storage_dir = ROOT / "data" / "test_uploads_be3"
    if storage_dir.exists():
        shutil.rmtree(storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    yield
