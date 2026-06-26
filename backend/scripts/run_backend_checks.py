from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMMANDS = [
    [sys.executable, "-m", "compileall", "app"],
    [sys.executable, "-c", "from app.main import app; print(app.title, app.version, len(app.openapi()['paths']))"],
    [sys.executable, "scripts/init_db.py"],
    [sys.executable, "scripts/validate_openapi.py"],
]


def main() -> int:
    for command in COMMANDS:
        print("$ " + " ".join(command))
        result = subprocess.run(command, cwd=ROOT, text=True)
        if result.returncode != 0:
            print(f"FAILED: {' '.join(command)}", file=sys.stderr)
            return result.returncode
    print("Backend checks completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
