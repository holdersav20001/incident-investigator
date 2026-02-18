"""Run three realistic incident scenarios against the live API.

Each scenario has a matching evidence log file in ./evidence/{job_name}/
so the LLM receives real log context in its diagnosis prompt.

Usage:
    python scripts/run_scenarios.py            # runs all 3 scenarios
    python scripts/run_scenarios.py --no-color # plain text (for CI / log capture)

The API must be running first:
    python main.py   (in another terminal)
"""

from __future__ import annotations

import argparse
import json
import sys
import textwrap
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import urllib.request
import urllib.error

API_BASE = "http://localhost:8000"

# ── ANSI colour helpers ──────────────────────────────────────────────────────

_USE_COLOR = True  # toggled by --no-color

def _c(code: str, text: str) -> str:
    return f"\033[{code}m{text}\033[0m" if _USE_COLOR else text

def bold(t: str)    -> str: return _c("1", t)
def green(t: str)   -> str: return _c("32", t)
def yellow(t: str)  -> str: return _c("33", t)
def red(t: str)     -> str: return _c("31", t)
def cyan(t: str)    -> str: return _c("36", t)
def dim(t: str)     -> str: return _c("2", t)
def magenta(t: str) -> str: return _c("35", t)

# ── HTTP helpers ─────────────────────────────────────────────────────────────

def _request(method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    url = f"{API_BASE}{path}"
    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            detail = json.loads(raw)
        except json.JSONDecodeError:
            detail = raw
        raise RuntimeError(f"HTTP {exc.code} {exc.reason}: {detail}") from exc


def get(path: str) -> dict[str, Any]:
    return _request("GET", path)


def post(path: str, body: dict | None = None) -> dict[str, Any]:
    return _request("POST", path, body)


# ── Scenario definitions ─────────────────────────────────────────────────────

SCENARIOS = [
    {
        "label": "CDC Orders — Schema Mismatch",
        "job_name": "cdc_orders",
        "source": "airflow",
        "environment": "prod",
        "error_type": "schema_mismatch",
        "error_message": (
            "Schema validation FAILED: column 'user_id' present in Kafka source "
            "(non-nullable long) is missing from target table analytics.orders_staging. "
            "PySpark AnalysisException: Resolved attribute user_id#42L missing from "
            "order_id#38, product_id#39, amount#40, created_at#41, updated_at#43."
        ),
    },
    {
        "label": "ETL Customers — Query Timeout",
        "job_name": "etl_customers",
        "source": "airflow",
        "environment": "prod",
        "error_type": "timeout",
        "error_message": (
            "psycopg2.OperationalError: canceling statement due to statement timeout. "
            "Query exceeded statement_timeout=3600000ms. Sequential scan on orders "
            "(89,432,871 rows) — missing index on orders.customer_id. "
            "Records written before timeout: 2,847,103 / 12,483,920 (22.8%). "
            "Table analytics.customers_staging is now in INCONSISTENT state."
        ),
    },
    {
        "label": "fact_sales_daily — Data Quality Failure",
        "job_name": "fact_sales_daily",
        "source": "airflow",
        "environment": "prod",
        "error_type": "data_quality",
        "error_message": (
            "dbt test FAILED: not_null_fact_sales_daily_product_id. "
            "1,243 rows with product_id=NULL (0.44% of 284,931 total). "
            "Pattern: ALL failures have payment_method='KLARNA'. "
            "Upstream: payments_api_ingest PARTIAL_SUCCESS — "
            "Klarna webhook v2 missing product_id field (API change 2026-02-18 04:00 UTC)."
        ),
    },
]


# ── Display helpers ──────────────────────────────────────────────────────────

def _divider(char: str = "-", width: int = 72) -> None:
    print(dim(char * width))


def _section(title: str) -> None:
    print()
    print(bold(cyan(f"  {title}")))
    _divider()


def _kv(key: str, value: str, indent: int = 4) -> None:
    pad = " " * indent
    print(f"{pad}{bold(key + ':')}  {value}")


def _wrap(text: str, indent: int = 6, width: int = 66) -> None:
    pad = " " * indent
    for line in textwrap.wrap(text, width):
        print(f"{pad}{line}")


def _status_badge(status: str) -> str:
    badges = {
        "APPROVED":          green(f"[{status}]"),
        "REJECTED":          red(f"[{status}]"),
        "APPROVAL_REQUIRED": yellow(f"[{status}]"),
        "RISK_ASSESSED":     yellow(f"[{status}]"),
        "DIAGNOSED":         cyan(f"[{status}]"),
        "CLASSIFIED":        cyan(f"[{status}]"),
        "RECEIVED":          dim(f"[{status}]"),
    }
    return badges.get(status, f"[{status}]")


def _risk_badge(level: str) -> str:
    return {
        "LOW":    green(level),
        "MEDIUM": yellow(level),
        "HIGH":   red(level),
    }.get(level, level)


# ── Print full incident result ───────────────────────────────────────────────

def _print_result(scenario: dict, incident: dict, elapsed_s: float) -> None:
    status = incident.get("status", "?")
    print()
    print("=" * 72)
    print(bold(f"  {scenario['label']}"))
    print(f"  {_status_badge(status)}  {dim(f'({elapsed_s:.1f}s total)')}")
    print("=" * 72)

    # ── Classification ──────────────────────────────────────────────────
    clf = incident.get("classification") or {}
    if clf:
        _section("1. Classification  (rule-based, no LLM)")
        _kv("Type",       clf.get("type", "?"))
        _kv("Confidence", f"{clf.get('confidence', 0):.0%}")
        _kv("Reason",     clf.get("reason") or clf.get("reasoning") or "—")
    else:
        _section("1. Classification")
        print("    (not completed)")

    # ── Diagnosis ───────────────────────────────────────────────────────
    diag = incident.get("diagnosis") or {}
    if diag:
        _section("2. Diagnosis  (LLM with log evidence)")
        rc = diag.get("root_cause") or diag.get("root_cause_summary") or "—"
        print(f"    {bold('Root cause:')}")
        _wrap(rc)
        conf = diag.get("confidence")
        if conf is not None:
            _kv("Confidence", f"{conf:.0%}")
        evidence = diag.get("evidence") or []
        if evidence:
            print(f"    {bold('Evidence cited:')}")
            for ev in evidence[:5]:
                src = ev.get("source", "?") if isinstance(ev, dict) else str(ev)
                snip = ev.get("snippet", "") if isinstance(ev, dict) else ""
                if snip:
                    print(f"      - [{src}] {snip[:80]}{'...' if len(snip) > 80 else ''}")
                else:
                    print(f"      - {src}")
        checks = diag.get("next_checks") or []
        if checks:
            print(f"    {bold('Next checks:')}")
            for ch in checks[:5]:
                _wrap(f"- {ch}", indent=6)
    else:
        _section("2. Diagnosis")
        print("    (not completed)")

    # ── Remediation ─────────────────────────────────────────────────────
    rem = incident.get("remediation") or {}
    if rem:
        _section("3. Remediation Plan  (LLM)")
        plan_steps = rem.get("plan") or []
        if plan_steps:
            print(f"    {bold('Plan:')}")
            for i, step in enumerate(plan_steps, 1):
                s = step.get("step", str(step)) if isinstance(step, dict) else str(step)
                cmd = step.get("command", "") if isinstance(step, dict) else ""
                _wrap(f"{i}. {s}", indent=6)
                if cmd:
                    print(f"       {dim('cmd:')} {dim(cmd)}")
        rollback = rem.get("rollback") or []
        if rollback:
            print(f"    {bold('Rollback:')}")
            for rb in rollback:
                s = rb.get("step", str(rb)) if isinstance(rb, dict) else str(rb)
                _wrap(f"- {s}", indent=6)
        eta = rem.get("expected_time_minutes")
        if eta is not None:
            _kv("Est. time", f"{eta} min")
    else:
        _section("3. Remediation")
        print("    (not completed)")

    # ── Simulation ──────────────────────────────────────────────────────
    sim = incident.get("simulation") or {}
    if sim:
        _section("4. Safety Simulation  (deterministic)")
        ok_val = sim.get("ok")
        ok_str = green("SAFE") if ok_val else red("UNSAFE")
        _kv("Result", ok_str)
        checks = sim.get("checks") or []
        if checks:
            for ch in checks[:6]:
                name  = ch.get("name", "?") if isinstance(ch, dict) else str(ch)
                passed = ch.get("passed", True) if isinstance(ch, dict) else True
                icon  = green("[PASS]") if passed else red("[FAIL]")
                print(f"      {icon} {name}")
        notes = sim.get("notes") or []
        if notes:
            print(f"    {bold('Notes:')}")
            for n in notes[:4]:
                _wrap(f"- {n}", indent=6)
    else:
        _section("4. Simulation")
        print("    (not completed)")

    # ── Risk ────────────────────────────────────────────────────────────
    risk = incident.get("risk") or {}
    if risk:
        _section("5. Risk Assessment  (deterministic)")
        score = risk.get("risk_score", "?")
        level = risk.get("risk_level", "?")
        _kv("Score", f"{score}/100  {_risk_badge(str(level))}")
        recommendation = risk.get("recommendation")
        if recommendation:
            _kv("Recommendation", recommendation)
        rationale = risk.get("rationale")
        if rationale:
            print(f"    {bold('Rationale:')}")
            _wrap(rationale)
        blast = risk.get("blast_radius") or []
        if blast:
            print(f"    {bold('Blast radius:')}")
            for b in blast[:5]:
                _wrap(f"- {b}", indent=6)
    else:
        _section("5. Risk")
        print("    (not completed)")

    # ── Decision ────────────────────────────────────────────────────────
    _section("6. Decision  (policy)")
    _kv("Final status", _status_badge(status))
    appr = incident.get("approval_status")
    if appr:
        _kv("Approval status", appr)

    _divider("=")
    print()


# ── Run one scenario ─────────────────────────────────────────────────────────

def run_scenario(scenario: dict) -> None:
    incident_id = str(uuid.uuid4())
    label = scenario["label"]

    print()
    _divider("*")
    print(bold(f"  Running: {label}"))
    print(f"  Job:     {scenario['job_name']}   |   Env: {scenario['environment']}")
    print(f"  ID:      {dim(incident_id)}")
    _divider("*")

    # Step 1: ingest
    print(f"\n  {cyan('>')} Ingesting event ...", end="", flush=True)
    t0 = time.monotonic()
    payload = {
        "incident_id": incident_id,
        "source": scenario["source"],
        "environment": scenario["environment"],
        "job_name": scenario["job_name"],
        "error_type": scenario["error_type"],
        "error_message": scenario["error_message"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    ingest_resp = post("/events/ingest", payload)
    print(f"  {green('[OK]')} status={ingest_resp.get('status')}")

    # Step 2: investigate  (may call LLM — can take a few seconds)
    print(f"  {cyan('>')} Running investigation pipeline (LLM calls in progress) ...", end="", flush=True)
    inv_resp = post(f"/incidents/{incident_id}/investigate")
    elapsed = time.monotonic() - t0
    print(f"  {green('[OK]')} final_status={inv_resp.get('final_status')}  ({elapsed:.1f}s)")

    # Step 3: fetch full record
    incident = get(f"/incidents/{incident_id}")

    _print_result(scenario, incident, elapsed)


# ── Main ─────────────────────────────────────────────────────────────────────

def _check_api() -> None:
    try:
        h = get("/health")
        status = h.get("status", "?")
        if status != "ok":
            print(yellow(f"[!!] API health status: {status}"))
    except Exception as exc:
        print(red(f"\n[!!] Cannot reach API at {API_BASE}"))
        print(f"     {exc}")
        print(f"\n     Start the server first:  python main.py\n")
        sys.exit(1)


def main() -> None:
    global _USE_COLOR  # noqa: PLW0603

    parser = argparse.ArgumentParser(description="Run realistic incident scenarios against the live API.")
    parser.add_argument("--no-color", action="store_true", help="Disable ANSI color output")
    parser.add_argument("--scenario", type=int, choices=[1, 2, 3],
                        help="Run only one scenario (1=cdc_orders, 2=etl_customers, 3=fact_sales_daily)")
    args = parser.parse_args()

    if args.no_color:
        _USE_COLOR = False

    # Ensure stdout handles the full Unicode range from LLM responses.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print()
    print(bold("=" * 72))
    print(bold("  Incident Investigator — Realistic Scenario Runner"))
    print(bold("=" * 72))
    print(f"  API:       {API_BASE}")
    print(f"  Evidence:  ./evidence/{{job_name}}/*.log  (sent verbatim to LLM)")
    print(f"  Date:      2026-02-18")

    _check_api()
    print(f"  {green('[OK]')} API is reachable")

    scenarios = SCENARIOS if args.scenario is None else [SCENARIOS[args.scenario - 1]]

    for i, scenario in enumerate(scenarios):
        try:
            run_scenario(scenario)
        except RuntimeError as exc:
            print(red(f"\n[!!] Scenario '{scenario['label']}' failed: {exc}\n"))
        # Brief cooldown between scenarios so the free-tier model isn't rate-limited
        # on the very next request.  Skipped after the final scenario.
        if i < len(scenarios) - 1:
            wait = 20
            print(dim(f"  (pausing {wait}s between scenarios to respect free-tier rate limits ...)"))
            time.sleep(wait)

    print(bold("  All scenarios complete."))
    print()


if __name__ == "__main__":
    main()
