#!/usr/bin/env python3
"""show_setup.py — snapshot of everything that was set up.

Run from the project root:
    python scripts/show_setup.py

Shows:
  - Which infrastructure files exist
  - Which source packages are present
  - Test counts per module
  - Docker daemon and container status (if Docker is available)
  - Postgres connectivity + schema tables (if DB is reachable)
  - Current Alembic migration revision (if DB is reachable)
  - API health (if the server happens to be running)
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# ---------------------------------------------------------------------------
# Colour helpers (works on Windows 10+ with ANSI enabled)
# ---------------------------------------------------------------------------

GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(text: str)   -> str: return f"{GREEN}[OK]{RESET} {text}"
def warn(text: str) -> str: return f"{YELLOW}[??]{RESET} {text}"
def fail(text: str) -> str: return f"{RED}[!!]{RESET} {text}"
def hdr(text: str)  -> str: return f"\n{BOLD}{CYAN}{text}{RESET}"
def row(label: str, value: str, width: int = 34) -> str:
    return f"  {label:<{width}} {value}"


def _check(path: Path, label: str | None = None) -> str:
    label = label or path.name
    return ok(label) if path.exists() else fail(label)


# ---------------------------------------------------------------------------
# Section 1 — Infrastructure files
# ---------------------------------------------------------------------------

def section_files() -> None:
    print(hdr("Infrastructure Files"))

    groups = {
        "Docker / Compose": [
            (ROOT / "Dockerfile",            "Dockerfile"),
            (ROOT / "docker-compose.yml",    "docker-compose.yml"),
            (ROOT / ".env.example",          ".env.example"),
        ],
        "Migrations": [
            (ROOT / "alembic.ini",           "alembic.ini"),
            (ROOT / "alembic" / "env.py",    "alembic/env.py"),
            (ROOT / "alembic" / "versions",  "alembic/versions/"),
        ],
        "CI": [
            (ROOT / ".github" / "workflows" / "ci.yml", ".github/workflows/ci.yml"),
        ],
        "Dev scripts": [
            (ROOT / "scripts" / "dev_up.ps1",  "scripts/dev_up.ps1"),
            (ROOT / "scripts" / "dev_down.ps1","scripts/dev_down.ps1"),
            (ROOT / "scripts" / "verify.ps1",  "scripts/verify.ps1"),
        ],
        "App config": [
            (ROOT / "main.py",                "main.py"),
            (ROOT / "src" / "investigator" / "config.py", "src/investigator/config.py"),
            (ROOT / ".env",                   ".env  (local overrides)"),
        ],
    }

    for group, entries in groups.items():
        print(f"\n  {BOLD}{group}{RESET}")
        for path, label in entries:
            exists = path.exists()
            marker = ok(label) if exists else fail(label)
            extra = ""
            if path.is_dir() and exists:
                n = len(list(path.glob("*.py")))
                extra = f"  ({n} files)"
            print(f"    {marker}{extra}")


# ---------------------------------------------------------------------------
# Section 2 — Source packages
# ---------------------------------------------------------------------------

def section_source() -> None:
    print(hdr("Source Packages  (src/investigator/)"))
    pkg_root = ROOT / "src" / "investigator"
    if not pkg_root.exists():
        print(fail("src/investigator/ not found"))
        return

    packages = sorted(
        d for d in pkg_root.iterdir()
        if d.is_dir() and not d.name.startswith("_")
    )
    for pkg in packages:
        n_files = len(list(pkg.glob("*.py")))
        print(f"  {ok(pkg.name):<40} {n_files} .py files")


# ---------------------------------------------------------------------------
# Section 3 — Test inventory
# ---------------------------------------------------------------------------

def section_tests() -> None:
    print(hdr("Test Inventory"))
    tests_root = ROOT / "tests"

    total_unit = 0
    print(f"\n  {'Module':<30} {'Tests':>6}")
    print(f"  {'-'*30} {'------':>6}")

    for d in sorted(tests_root.iterdir()):
        if not d.is_dir() or d.name.startswith("_") or d.name == "integration":
            continue
        n = sum(1 for f in d.glob("test_*.py") for line in f.read_text(encoding="utf-8").splitlines() if line.strip().startswith("def test_"))
        if n:
            total_unit += n
            print(f"  {d.name:<30} {n:>6}")

    print(f"  {'-'*30} {'------':>6}")
    print(f"  {'UNIT TOTAL':<30} {total_unit:>6}")

    integ_dir = tests_root / "integration"
    if integ_dir.exists():
        n_integ = sum(1 for f in integ_dir.glob("test_*.py") for line in f.read_text(encoding="utf-8").splitlines() if line.strip().startswith("def test_"))
        print(f"  {'integration  (requires Docker)':<30} {n_integ:>6}")
        print(f"  {'GRAND TOTAL':<30} {total_unit + n_integ:>6}")


# ---------------------------------------------------------------------------
# Section 4 — Docker status
# ---------------------------------------------------------------------------

def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return -1, ""


def section_docker() -> None:
    print(hdr("Docker"))

    code, out = _run(["docker", "info", "--format", "{{.ServerVersion}}"])
    if code != 0:
        print(f"  {warn('Docker daemon not reachable (skipping container checks)')}")
        return
    print(f"  {ok(f'Docker daemon running  (server {out})')}")

    # Compose services
    code, out = _run(
        ["docker", "compose", "--project-directory", str(ROOT), "ps", "--format", "table {{.Name}}\t{{.Status}}"]
    )
    if code == 0 and out:
        lines = out.strip().splitlines()
        print(f"\n  {'Container':<30} {'Status'}")
        print(f"  {'-'*30} {'-'*20}")
        for line in lines[1:] if lines[0].startswith("NAME") else lines:
            parts = line.split("\t", 1)
            name   = parts[0].strip() if parts else line
            status = parts[1].strip() if len(parts) > 1 else "?"
            colour = GREEN if "healthy" in status.lower() or "running" in status.lower() else YELLOW
            print(f"  {name:<30} {colour}{status}{RESET}")
    else:
        print(f"  {warn('No compose services running  (run: .\\scripts\\dev_up.ps1)')}")


# ---------------------------------------------------------------------------
# Section 5 — Postgres connectivity + schema
# ---------------------------------------------------------------------------

def section_database() -> None:
    print(hdr("Database  (Postgres)"))

    db_url = os.environ.get("DATABASE_URL", "postgresql://incidents:incidents@localhost:5432/incidents")
    print(f"  {row('DATABASE_URL', db_url)}")

    if not db_url.startswith(("postgresql://", "postgres://")):
        print(f"  {warn('DATABASE_URL is not Postgres — skipping connectivity check')}")
        return

    if importlib.util.find_spec("sqlalchemy") is None:
        print(f"  {warn('sqlalchemy not installed')}")
        return

    try:
        from sqlalchemy import create_engine, inspect, text
        engine = create_engine(db_url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
        print(f"  {ok('Connected')}")
        print(f"  {row('Server', version.split(',')[0])}")

        # Tables
        inspector = inspect(engine)
        tables = sorted(inspector.get_table_names())
        expected = {"incidents", "incident_events", "transitions", "approvals", "feedback"}
        print(f"\n  {'Table':<30} {'Rows':>8}")
        print(f"  {'-'*30} {'--------':>8}")
        for t in tables:
            if t == "alembic_version":
                continue
            marker = ok if t in expected else warn
            with engine.connect() as conn:
                n = conn.execute(text(f"SELECT COUNT(*) FROM {t}")).scalar()
            status = "expected" if t in expected else "extra"
            print(f"  {marker(t):<40} {n:>8}  ({status})")

        missing = expected - set(tables)
        for t in sorted(missing):
            print(f"  {fail(t):<40} {'missing':>8}")

        # Alembic revision
        with engine.connect() as conn:
            rev = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
        print(f"\n  {ok(f'Alembic revision: {rev}')}")
        engine.dispose()

    except Exception as exc:
        short = str(exc).splitlines()[0][:80]
        print(f"  {fail(f'Cannot connect: {short}')}")
        print(f"  {warn('Start the DB:  .\\scripts\\dev_up.ps1')}")


# ---------------------------------------------------------------------------
# Section 6 — API health
# ---------------------------------------------------------------------------

def section_api() -> None:
    print(hdr("API  (FastAPI)"))

    if importlib.util.find_spec("urllib") is None:
        return

    import urllib.request, urllib.error  # noqa: E401
    url = "http://localhost:8000/health"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            body = resp.read().decode()
            print(f"  {ok(f'GET /health → {resp.status}')}")
            import json
            data = json.loads(body)
            print(f"  {row('status', data.get('status', '?'))}")
            db_ok = data.get("db", {}).get("reachable", False)
            print(f"  {row('db.reachable', str(db_ok))}")
    except urllib.error.URLError:
        print(f"  {warn('API not running on localhost:8000  (run: python main.py)')}")
    except Exception as exc:
        print(f"  {warn(str(exc)[:80])}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # Enable ANSI on Windows
    if sys.platform == "win32":
        os.system("")

    print(f"{BOLD}{'='*60}{RESET}")
    print(f"{BOLD}  Autonomous Data Incident Investigator - Setup Status{RESET}")
    print(f"{BOLD}{'='*60}{RESET}")
    print(f"  Project root: {ROOT}")

    section_files()
    section_source()
    section_tests()
    section_docker()
    section_database()
    section_api()

    print(f"\n{BOLD}{'='*60}{RESET}\n")


if __name__ == "__main__":
    main()
