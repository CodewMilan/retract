"""Prepare reviewable Codex files locally; never edits the user's Codex settings."""

import argparse
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from retract.mcp_tools import LocalApi


def toml_value(value):
    if isinstance(value, dict):
        return "{" + ", ".join(f"{json.dumps(key)} = {toml_value(item)}" for key, item in value.items()) + "}"
    if isinstance(value, list):
        return "[" + ", ".join(toml_value(item) for item in value) + "]"
    return json.dumps(value, ensure_ascii=False)


def settings(root: Path, python: Path, api_url: str, report_dir: Path, confirm_revision: bool = False) -> dict:
    LocalApi(api_url)
    # Non-interactive `codex exec` rejects tools that need approval; only the
    # developer's explicit flag pre-approves the one confirmed plan revision.
    approvals = {"tools": {"revise_plan": {"approval_mode": "approve"}}} if confirm_revision else {}
    return {
        # Resolving a venv's executable symlink would discard its site-packages.
        "command": str(python.expanduser().absolute()),
        "args": ["-m", "retract", "mcp", "--activity-log", str((report_dir / "mcp-activity.jsonl").resolve())],
        "cwd": str(root.resolve()),
        "env": {"PYTHONPATH": str((root / "src").resolve()), "RETRACT_URL": api_url},
        "startup_timeout_sec": 10, "tool_timeout_sec": 90, "required": True,
        "enabled_tools": ["remember", "process_update", "recall", "history", "record_plan", "revise_plan", "handoff", "claim_handoff"],
        **approvals,
    }


PROMPT = ("Follow examples/account-settings/AGENT_TASK.md. Call RETRACT recall before planning. If recall lists an "
          "open handoff for agent codex, claim it with claim_handoff as agent codex, report its warnings, and treat its "
          "draft as a proposal to verify against the repository, not as accepted memory. Inspect the current "
          "repository, implement the settings page, and run meaningful feature tests. Report actual sources, tool "
          "calls, and failures.")
CONFIRMATION = (" The developer confirms in advance: after you have checked the handoff draft against the code, you "
                "may call revise_plan once for the flagged plan, citing only active fact IDs you relied on.")


def prepare(report_dir: Path, *, python: Path, api_url: str, check: bool = False, workspace: Path = ROOT,
            confirm_revision: bool = False) -> dict:
    report_dir = report_dir.resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    if not (workspace / "examples/account-settings/AGENT_TASK.md").is_file():
        raise ValueError("Workspace must be a Retract checkout containing examples/account-settings/AGENT_TASK.md")
    config = settings(ROOT, python, api_url, report_dir, confirm_revision)
    snippet = "[mcp_servers.retract]\n" + "\n".join(f"{key} = {toml_value(value)}" for key, value in config.items()) + "\n"
    (report_dir / "codex.retract.toml").write_text(snippet)
    override = "mcp_servers.retract=" + toml_value(config)
    command = ["codex", "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--sandbox", "workspace-write",
               "-C", str(workspace.resolve()), "-c", override, PROMPT + (CONFIRMATION if confirm_revision else "")]
    script = "#!/bin/sh\nset -eu\n" + shlex.join(command) + " > " + shlex.quote(str(report_dir / "codex-session.jsonl")) + "\n"
    (report_dir / "start-codex-retract.sh").write_text(script)
    result = {"configuration": str(report_dir / "codex.retract.toml"),
              "launch_script": str(report_dir / "start-codex-retract.sh"),
              "workspace": str(workspace.resolve()), "developer_confirmed_revision": confirm_revision,
              "user_settings_modified": False, "configuration_recognized": "not_checked",
              "coding_client_recall_observed": False}
    if check:
        executable = shutil.which("codex")
        if not executable:
            raise RuntimeError("Codex CLI not found; generated files are ready for review")
        checked = subprocess.run([executable, "mcp", "get", "retract", "--json", "-c", override],
                                 cwd=ROOT, capture_output=True, text=True, timeout=15)
        if checked.returncode:
            raise RuntimeError("Codex rejected the configuration; inspect the generated TOML and local CLI version")
        parsed = json.loads(checked.stdout)
        transport = parsed.get("transport", {})
        if transport.get("command") != config["command"] or transport.get("args") != config["args"]:
            raise RuntimeError("Codex resolved a different MCP transport configuration")
        version = subprocess.run([executable, "--version"], capture_output=True, text=True, timeout=5)
        result.update(configuration_recognized=True, client_version=version.stdout.strip())
    (report_dir / "codex-configuration.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "reports/phase3")
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--api-url", default="http://127.0.0.1:8100")
    parser.add_argument("--check", action="store_true", help="Ask the installed Codex CLI to parse the config; does not start an agent")
    parser.add_argument("--workspace", type=Path, default=ROOT,
                        help="Checkout Codex works in (for example a pre-frontend baseline); MCP tools still run from this checkout")
    parser.add_argument("--developer-confirms-revision", action="store_true",
                        help="State in the prompt that the developer pre-approves one revise_plan call after verification")
    args = parser.parse_args()
    try:
        result = prepare(args.report_dir, python=args.python, api_url=args.api_url, check=args.check,
                         workspace=args.workspace, confirm_revision=args.developer_confirms_revision)
        print(json.dumps(result, indent=2))
    except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
