"""Offline Phase 3 tests and optional real MCP-to-memory-service probe.

The probe is a programmatic MCP client, not evidence of a real coding-agent call.
Client traces and frontend feature checks remain separate exit-gate evidence.
"""

import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from retract.mcp import VERSIONS
from retract.mcp_tools import LocalApi


def probe(api_url: str) -> dict:
    LocalApi(api_url)
    frames = [{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": VERSIONS[0], "capabilities": {}, "clientInfo": {"name": "retract-phase3-probe", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"}]
    for request_id, name, arguments in (
        (2, "recall", {"project_id": "account-settings", "scope": "web-client/main", "subjects": ["browser-api"]}),
        (3, "recall", {"project_id": "account-settings", "scope": "account-service/main", "subjects": ["profile"]}),
        (4, "history", {"project_id": "account-settings", "fact_id": "F1"}),
    ):
        frames.append({"jsonrpc": "2.0", "id": request_id, "method": "tools/call", "params": {"name": name, "arguments": arguments}})
    completed = subprocess.run([sys.executable, "-m", "retract", "mcp"], cwd=ROOT,
                               env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "RETRACT_URL": api_url},
                               input="".join(json.dumps(frame) + "\n" for frame in frames), text=True,
                               capture_output=True, timeout=55)
    if completed.returncode:
        raise RuntimeError("MCP subprocess exited unsuccessfully")
    messages = [json.loads(line) for line in completed.stdout.splitlines()]
    if [row.get("id") for row in messages] != [1, 2, 3, 4]:
        raise RuntimeError("Incomplete MCP probe responses")
    values = []
    for message in messages[1:]:
        result = message.get("result", {})
        if result.get("isError") is not False:
            raise RuntimeError("MCP probe could not retrieve real memory; start and seed the service, apply U1, and retry")
        values.append(json.loads(result["content"][0]["text"]))
    web, account, history = values
    if not any(fact["id"] == "F5" and fact["status"] == "active" for fact in web["active_facts"]) or any(fact["id"] == "F1" for fact in web["active_facts"]):
        raise RuntimeError("Probe requires the declared U1 fixture: current F5 and superseded F1")
    if not any(fact["id"] == "F4" and fact["status"] == "active" for fact in account["active_facts"]):
        raise RuntimeError("Ownership fact F4 was not retrieved")
    if {fact["id"] for fact in history["facts"]} != {"F1", "F5"}:
        raise RuntimeError("Historical replacement chain is incomplete")
    return {"status": "passed", "client": "programmatic-stdio-probe", "coding_client_recall_observed": False,
            "web_fact_ids": [fact["id"] for fact in web["active_facts"]],
            "ownership_fact_ids": [fact["id"] for fact in account["active_facts"]],
            "source_ids": sorted({item["source"]["id"] for value in (web, account) for item in value["sources"]}),
            "project_revision": web["project_revision"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", action="store_true", help="Actually call recall/history through a new MCP process and running memory API")
    parser.add_argument("--sdk", action="store_true", help="Require the optional official Python SDK interoperability test")
    parser.add_argument("--postgres", action="store_true", help="Require real profile-store tests against the already running demo PostgreSQL")
    parser.add_argument("--api-url", default="http://127.0.0.1:8100")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/phase3.json")
    args = parser.parse_args()
    report = {"phase": 3, "recorded_at": datetime.now(timezone.utc).isoformat(), "status": "running",
              "coding_client_recall_observed": False, "frontend_feature_checks": "not_run",
              "sdk_interoperability": "not_run", "real_memory_probe": "not_run", "postgresql_fixture": "not_verified"}
    status = 1
    try:
        completed = subprocess.run([sys.executable, "-m", "unittest", "tests.test_mcp", "tests.test_demo", "tests.test_codex_configuration", "-v"],
                                   cwd=ROOT, env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
        if completed.returncode:
            raise RuntimeError("Phase 3 offline tests failed")
        report["offline_tests"] = "passed"
        if args.sdk:
            if importlib.util.find_spec("mcp") is None:
                raise RuntimeError("Official MCP SDK missing; install .[mcp-test] to run --sdk")
            checked = subprocess.run([sys.executable, "-m", "unittest", "tests.test_mcp_sdk", "-v"], cwd=ROOT,
                                     env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
            if checked.returncode:
                raise RuntimeError("Official SDK interoperability test failed")
            report["sdk_interoperability"] = "passed"
        if args.postgres:
            if importlib.util.find_spec("psycopg") is None:
                raise RuntimeError("PostgreSQL client missing; install .[demo] to run --postgres")
            checked = subprocess.run([sys.executable, "-m", "unittest", "tests.test_demo_postgres", "-v"], cwd=ROOT,
                                     env={**os.environ, "PYTHONPATH": str(ROOT / "src"), "RUN_DEMO_POSTGRES_TESTS": "1"})
            if checked.returncode:
                raise RuntimeError("Real demo PostgreSQL tests failed")
            report["postgresql_fixture"] = "passed"
        if args.probe:
            report["real_memory_probe"] = probe(args.api_url)
        report["status"] = "offline_passed_client_feature_gate_unverified"
        status = 0
    except (RuntimeError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        report.update(status="blocked_or_failed", error=str(exc))
        print(f"Phase 3 did not pass its requested checks: {exc}", file=sys.stderr)
    finally:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Phase 3: {report['status']}. Report: {args.report}", flush=True)
    raise SystemExit(status)


if __name__ == "__main__":
    main()
