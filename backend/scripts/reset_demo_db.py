from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/refcheck_demo.db")
os.environ.setdefault("FILE_STORAGE_DIR", "./data/demo_uploads")

from app.db.init_db import drop_db_for_tests_only, init_db  # noqa: E402

if __name__ == "__main__":
    drop_db_for_tests_only()
    init_db()
    print("Demo database reset and initialized.")
