"""Phase 2 checks. --live additionally calls Groq on declared synthetic cases.

Offline tests prove adapter/policy behavior with controlled responses, not model
accuracy. Live evaluation checks extraction plus pure policy; it does not replace
Phase 1's database and restart gate.
"""

from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import argparse


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from retract.inference import GroqInterpreter, ModelError, PROMPT_VERSION
from retract.models import NaturalUpdateInput, SourceInput, ValidationError
from retract.policy import decide


def load_cases():
    dataset = json.loads((ROOT / "fixtures/classification-eval.json").read_text())
    seed = json.loads((ROOT / "fixtures/demo-seed.json").read_text())
    facts = {}
    for action in seed["actions"]:
        if action["route"] == "remember":
            body = action["body"]
            facts[(body["scope"], body["subject"], body["predicate"])] = {
                **{key: body[key] for key in ("project_id", "scope", "subject", "predicate", "value")},
                "id": body["fact_id"], "status": "active",
            }
    cases = []
    seen = set()
    for row in dataset["cases"]:
        if row["id"] in seen:
            raise ValidationError("Evaluation case IDs must be unique")
        seen.add(row["id"])
        source = SourceInput(id="source-" + row["id"], kind="developer", title="Synthetic evaluation source",
                             content=row["text"], authority=row["source_authority"])
        request = NaturalUpdateInput(
            project_id="account-settings", scope=row["scope"], subject=row["subject"], predicate=row["predicate"],
            event_id="eval-" + row["id"], text=row["text"], source=source, confirmation=row["confirmation"],
        )
        cases.append((row, request, facts[(row["scope"], row["subject"], row["predicate"])]))
    return dataset["version"], cases


def evaluate_cases(interpreter, cases, interval: float = 8, sleep=time.sleep) -> dict:
    if not cases:
        raise ValidationError("Live evaluation requires a nonempty declared case set")
    results = []
    for index, (expected, request, current) in enumerate(cases):
        if index:
            sleep(interval)
        print(f"Evaluating {index + 1}/{len(cases)}: {expected['id']}", flush=True)
        row = {"id": expected["id"], "expected_classification": expected["expected_classification"],
               "expected_outcome": expected["expected_outcome"]}
        try:
            interpretation = interpreter.extract(request, current)
            structured = interpretation.extraction.to_update(request, current, 0)
            decision = decide(structured, current)
            row.update(classification=interpretation.extraction.classification,
                       effective_classification=structured.classification, policy_outcome=decision.outcome,
                       classification_correct=interpretation.extraction.classification == expected["expected_classification"],
                       policy_correct=decision.outcome == expected["expected_outcome"],
                       interpretation=interpretation.audit())
        except (ModelError, ValidationError) as exc:
            row["error"] = str(exc)
        results.append(row)
        # A quota/access/configuration failure should not fan out more requests.
        if "error" in row:
            break
    completed = [row for row in results if "error" not in row]
    latencies = sorted(row["interpretation"]["elapsed_ms"] for row in completed)
    classification_correct = sum(row["classification_correct"] for row in completed)
    policy_correct = sum(row["policy_correct"] for row in completed)
    wrong_applications = sum(row["policy_outcome"] == "applied" and row["expected_outcome"] != "applied" for row in completed)
    usage_totals = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if completed and all(key in row["interpretation"]["usage"] for row in completed):
            usage_totals[key] = sum(row["interpretation"]["usage"][key] for row in completed)
    return {
        "passed": len(completed) == len(cases) and classification_correct == len(cases) and policy_correct == len(cases),
        "total_cases": len(cases), "evaluated_cases": len(completed),
        "request_errors": len(results) - len(completed), "not_run": len(cases) - len(results),
        "classification_correct": classification_correct, "policy_correct": policy_correct,
        "classification_accuracy": classification_correct / len(completed) if completed else None,
        "wrong_application_decisions": wrong_applications,
        "latency_ms": {"p50": round(statistics.median(latencies), 3),
                       "p95": latencies[math.ceil(0.95 * len(latencies)) - 1]} if latencies else None,
        "reported_usage_totals": usage_totals,
        "usage_note": "Only provider-reported counters from successful responses; retry/failure token usage is unknown.",
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="Call the configured Groq model on the synthetic evaluation set")
    parser.add_argument("--interval", type=float, default=8, help="Seconds between live cases (default 8)")
    parser.add_argument("--report", type=Path, default=ROOT / "reports/phase2.json")
    args = parser.parse_args()
    if not math.isfinite(args.interval) or args.interval < 0:
        parser.error("--interval must be a nonnegative finite number")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    report = {"phase": 2, "status": "running", "prompt_version": PROMPT_VERSION,
              "recorded_at": datetime.now(timezone.utc).isoformat(), "live_evaluation": "not_run",
              "database_gate": "separate_phase1_verification_required"}
    status = 1
    try:
        completed = subprocess.run([sys.executable, "-m", "unittest", "tests.test_inference", "tests.test_natural_updates",
                                    "tests.test_phase2_evaluation", "-v"], cwd=ROOT,
                                   env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
        report["offline_tests"] = "passed" if completed.returncode == 0 else "failed"
        if completed.returncode:
            report["status"] = "failed"
        elif not args.live:
            report["status"] = "offline_passed_live_unverified"
            status = 0
        else:
            interpreter = GroqInterpreter.from_env()
            dataset, cases = load_cases()
            report.update(dataset=dataset, configured_model=interpreter.model)
            evaluation = evaluate_cases(interpreter, cases, args.interval)
            report["live_evaluation"] = evaluation
            report["status"] = "model_policy_passed_database_gate_separate" if evaluation["passed"] else "failed"
            status = 0 if evaluation["passed"] else 1
    except (ModelError, ValidationError, OSError, ValueError, KeyError) as exc:
        report.update(status="blocked", error=str(exc))
        print(f"Phase 2 live evaluation did not run: {exc}", file=sys.stderr)
    finally:
        args.report.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Phase 2: {report['status']}. Report: {args.report}", flush=True)
    raise SystemExit(status)


if __name__ == "__main__":
    main()
