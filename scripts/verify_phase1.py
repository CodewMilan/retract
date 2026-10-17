"""Run Phase 1's actual gate, including database and application restarts.

Run from the repository with the project installed in an activated environment:
    python scripts/verify_phase1.py

This owns only UUID-named Docker Compose resources. A failed run preserves its
database for inspection and prints the exact cleanup command. No production
graph, volume, or service is reset or restarted.
"""

import argparse
import importlib.util
from importlib.metadata import version
import json
import os
from pathlib import Path
import shlex
import socket
import subprocess
import sys
import time
import traceback
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]


class GateFailure(RuntimeError):
    pass


def require(condition: bool, reason: str):
    if not condition:
        raise GateFailure(reason)


def assert_demo_state(snapshot: dict):
    """Check the declared fixture outcomes independently of the implementation."""
    web = snapshot["web"]
    cli = snapshot["cli"]
    account = snapshot["account"]
    history = snapshot["history"]
    require([(fact["id"], fact["value"], fact["status"]) for fact in web["active_facts"]]
            == [("F5", "HTTP-only cookie sessions", "active")], "Web recall must contain only current F5")
    require([(fact["id"], fact["value"], fact["status"]) for fact in cli["active_facts"]]
            == [("F2", "bearer tokens", "active")], "CLI authentication changed unexpectedly")
    require({fact["id"]: (fact["value"], fact["status"]) for fact in account["active_facts"]}
            == {"F3": ("PostgreSQL", "active"), "F4": ("own profile only", "active")},
            "Unrelated database or ownership facts changed")
    require([(warning["plan"]["id"], warning["plan"]["status"]) for warning in web["affected_plans"]]
            == [("P1", "needs_review")], "The explicitly dependent plan must need review")
    paths = web["affected_plans"][0]["explanation_paths"]
    require(any(path["event_id"] == "U1" and path["fact_id"] == "F1" and path["plan_id"] == "P1"
                for path in paths), "Plan warning is missing the stored dependency explanation")
    require({fact["id"]: fact["status"] for fact in history["facts"]}
            == {"F1": "superseded", "F5": "active"}, "Historical F1 or current F5 is missing")
    require(history["replacement_links"] == [{"new_fact_id": "F5", "old_fact_id": "F1"}],
            "Replacement relationship is missing")
    require({item["source"]["id"] for item in history["sources"]} == {"S-F1", "S-U1"},
            "Historical or replacement evidence is missing")
    require(snapshot["correction"]["event"]["outcome"] == "applied", "Confirmed correction did not apply")
    require(snapshot["proposal"]["event"]["outcome"] == "proposal", "Question was not preserved as a proposal")
    require(snapshot["proposal"]["event"]["accepted_fact_ids"] == [], "Proposal accepted a fact")
    require({snapshot[key]["project_revision"] for key in snapshot} == {7},
            "Unexpected revision: fixture must be seeded once, followed by U1 and U2")


def request(base: str, route: str, body: dict | None = None) -> dict:
    encoded = None if body is None else json.dumps(body).encode()
    req = Request(base + route, data=encoded, headers={"Content-Type": "application/json"})
    with urlopen(req, timeout=10) as response:
        return json.load(response)


def snapshot(base: str) -> dict:
    project = {"project_id": "account-settings"}
    return {
        "web": request(base, "/recall", {**project, "scope": "web-client/main"}),
        "cli": request(base, "/recall", {**project, "scope": "cli-client/main"}),
        "account": request(base, "/recall", {**project, "scope": "account-service/main"}),
        "history": request(base, "/history", {**project, "fact_id": "F1"}),
        "correction": request(base, "/history", {**project, "event_id": "U1"}),
        "proposal": request(base, "/history", {**project, "event_id": "U2"}),
    }


def command(args: list[str], *, env: dict | None = None, capture: bool = False) -> str:
    completed = subprocess.run(args, cwd=ROOT, env=env, text=True,
                               stdout=subprocess.PIPE if capture else None,
                               stderr=subprocess.PIPE if capture else None)
    if completed.returncode:
        if capture and completed.stderr:
            print(completed.stderr, file=sys.stderr, end="")
        raise GateFailure(f"Command failed ({completed.returncode}): {shlex.join(args)}")
    return completed.stdout or ""


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_service(env: dict, port: int, logfile):
    process = subprocess.Popen([sys.executable, "-m", "retract", "serve", "--port", str(port)],
                               cwd=ROOT, env=env, stdout=logfile, stderr=subprocess.STDOUT)
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 30
    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise GateFailure("Application exited before becoming healthy; inspect the service log")
            try:
                health = request(base, "/health")
                require(health == {"status": "ok", "storage": "falkordb"}, "Unexpected service health response")
                return process, base
            except (URLError, TimeoutError, ConnectionError):
                time.sleep(0.2)
        raise GateFailure("Application did not become healthy within 30 seconds")
    except BaseException:
        stop_service(process)
        raise


def stop_service(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def run(report_dir: Path, keep: bool = False) -> int:
    report_dir.mkdir(parents=True, exist_ok=True)
    report = {"phase": 1, "status": "running", "checks": [], "python": sys.version,
              "database_image": "falkordb/falkordb:6.0.2"}
    process = None
    started_database = False
    project_name = f"retract-verify-{uuid4().hex[:12]}"
    compose = ["docker", "compose", "-p", project_name, "-f", str(ROOT / "compose.verify.yaml")]
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    # Never reuse caller-selected storage or client endpoints in an isolated run.
    for key in ("FALKORDB_PASSWORD", "RUN_FALKORDB_TESTS", "RETRACT_URL"):
        env.pop(key, None)

    def check(name: str, action):
        print(f"Phase 1: {name}", flush=True)
        result = action()
        report["checks"].append({"name": name, "status": "passed"})
        return result

    try:
        check("offline tests", lambda: command(
            [sys.executable, "-m", "unittest", "tests.test_policy", "tests.test_service", "tests.test_api", "tests.test_http", "tests.test_verification", "-v"], env=env))
        require(importlib.util.find_spec("falkordb") is not None,
                "FalkorDB client is missing. Activate .venv and run python -m pip install -e .")
        report["falkordb_client"] = version("falkordb")
        check("Docker daemon", lambda: command(["docker", "info"], capture=True))
        started_database = True  # Also clean up partial startup after errors.
        check("isolated persistent FalkorDB startup", lambda: command(compose + ["up", "-d", "--wait"]))
        address = command(compose + ["port", "falkordb", "6379"], capture=True).strip()
        host, port = address.rsplit(":", 1)
        require(host == "127.0.0.1" and port.isdigit(), "Unexpected verification database address")
        env.update(FALKORDB_HOST="127.0.0.1", FALKORDB_PORT=port,
                   FALKORDB_GRAPH=f"retract-verify-{uuid4().hex}", RUN_FALKORDB_TESTS="1")
        report["compose_project"] = project_name

        def durability():
            raw = command(compose + ["exec", "-T", "falkordb", "redis-cli", "--raw", "CONFIG", "GET",
                                      "appendonly", "appendfsync", "dir"], capture=True).splitlines()
            settings = dict(zip(raw[::2], raw[1::2], strict=True))
            require(settings.get("appendonly") == "yes" and settings.get("appendfsync") == "always"
                    and settings.get("dir") == "/var/lib/falkordb/data", "Database durability configuration differs from the declared configuration")
            report["durability"] = settings
        check("actual durability configuration", durability)
        check("real database integration suite", lambda: command(
            [sys.executable, "-m", "unittest", "tests.test_integration", "-v"], env=env))
        api_port = free_port()
        with (report_dir / "service.log").open("w") as logfile:
            process, base = start_service(env, api_port, logfile)
            fixture = json.loads((ROOT / "fixtures/demo-seed.json").read_text())
            request(base, "/projects", fixture["project"])
            for action in fixture["actions"]:
                request(base, "/" + action["route"], action["body"])
            correction = json.loads((ROOT / "fixtures/confirmed-update.json").read_text())
            original_result = request(base, "/updates", correction)
            request(base, "/updates", json.loads((ROOT / "fixtures/proposal.json").read_text()))
            before = snapshot(base)
            check("HTTP fixture acceptance", lambda: assert_demo_state(before))
            (report_dir / "before-restart.json").write_text(json.dumps(before, indent=2) + "\n")
            stop_service(process)
            process = None
            command(compose + ["restart", "falkordb"])
            command(compose + ["up", "-d", "--wait"])
            process, base = start_service(env, api_port, logfile)
            after = snapshot(base)  # Deliberately no project creation or seed calls.
            (report_dir / "after-restart.json").write_text(json.dumps(after, indent=2) + "\n")
            def restart_check():
                assert_demo_state(after)
                require(after == before, "Facts, IDs, evidence, plans, revisions, or history changed after restart")
                require(request(base, "/updates", correction) == original_result, "Event replay changed after restart")
                require(snapshot(base) == after, "Replayed correction mutated state after restart")
            check("database and service restart without reseeding", restart_check)
        report["status"] = "passed"
        return 0
    except (GateFailure, OSError, ValueError) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        print(f"Phase 1 did not pass: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        report["status"] = "interrupted"
        return 130
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        traceback.print_exc()
        return 1
    finally:
        stop_service(process)
        if started_database:
            if report["status"] == "passed" and not keep:
                try:
                    command(compose + ["down", "--volumes"])
                except (GateFailure, OSError) as exc:
                    report["cleanup_error"] = str(exc)
                    print(f"Cleanup pending: {shlex.join(compose + ['down', '--volumes'])}", file=sys.stderr)
            else:
                report["cleanup_command"] = shlex.join(compose + ["down", "--volumes"])
                print(f"Verification data preserved. Cleanup: {report['cleanup_command']}", flush=True)
        path = report_dir / "phase1.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Phase 1 report: {path}", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "reports" / f"phase1-{uuid4().hex[:12]}")
    parser.add_argument("--keep", action="store_true", help="Keep this run's isolated database after success")
    args = parser.parse_args()
    raise SystemExit(run(args.report_dir.resolve(), args.keep))


if __name__ == "__main__":
    main()
