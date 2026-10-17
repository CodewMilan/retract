from contextlib import redirect_stdout
from io import StringIO
from types import SimpleNamespace
import unittest

from scripts.verify_phase2 import evaluate_cases, load_cases
from retract.inference import Extraction, Interpretation, ModelRateLimited, build_payload
from retract.models import Candidate, ValidationError


class FixtureInterpreter:
    """Known responses for testing report arithmetic, not model quality."""

    def __init__(self, cases, wrong=False):
        self.expected = {request.event_id: row for row, request, _ in cases}
        self.wrong = wrong

    def extract(self, request, current):
        classification = self.expected[request.event_id]["expected_classification"]
        if self.wrong:
            classification = "confirmed_change"
        candidate = Candidate(request.subject, request.predicate, "replacement", request.text) if classification == "confirmed_change" else None
        return Interpretation(Extraction(classification, request.scope, candidate), "test-fixture", 1,
                              {"prompt_tokens": 5, "completion_tokens": 5, "total_tokens": 10}, 1)


class EvaluationTests(unittest.TestCase):
    def test_empty_evaluation_cannot_pass(self):
        with self.assertRaises(ValidationError):
            evaluate_cases(FixtureInterpreter([]), [])

    def test_declared_dataset_is_valid_and_labels_are_never_sent_to_model(self):
        version, cases = load_cases()
        self.assertEqual(version, "retract-classification-eval-v1")
        self.assertEqual(len(cases), 16)
        self.assertEqual({row["expected_classification"] for row, _, _ in cases},
                         {"confirmed_change", "proposal", "ambiguous", "unrelated"})
        for _, request, current in cases:
            payload = build_payload(request, current, "test-fixture")
            self.assertNotIn("expected_classification", str(payload))
            self.assertNotIn("expected_outcome", str(payload))

    def test_metric_calculation_for_known_responses(self):
        _, cases = load_cases()
        with redirect_stdout(StringIO()):
            result = evaluate_cases(FixtureInterpreter(cases), cases, interval=0, sleep=lambda _: None)
        self.assertTrue(result["passed"])
        self.assertEqual(result["classification_correct"], 16)
        self.assertEqual(result["policy_correct"], 16)
        self.assertEqual(result["reported_usage_totals"]["total_tokens"], 160)
        self.assertEqual(result["wrong_application_decisions"], 0)

    def test_wrong_decisions_fail_the_declared_gate(self):
        _, cases = load_cases()
        with redirect_stdout(StringIO()):
            result = evaluate_cases(FixtureInterpreter(cases, wrong=True), cases, interval=0, sleep=lambda _: None)
        self.assertFalse(result["passed"])
        self.assertGreater(result["wrong_application_decisions"], 0)
        self.assertLess(result["classification_accuracy"], 1)

    def test_rate_limit_stops_requests_and_does_not_fabricate_metrics(self):
        _, cases = load_cases()
        def unavailable(*args):
            raise ModelRateLimited(60)
        with redirect_stdout(StringIO()):
            result = evaluate_cases(SimpleNamespace(extract=unavailable), cases, interval=0, sleep=lambda _: None)
        self.assertFalse(result["passed"])
        self.assertEqual(result["evaluated_cases"], 0)
        self.assertEqual(result["request_errors"], 1)
        self.assertEqual(result["not_run"], 15)
        self.assertIsNone(result["classification_accuracy"])
        self.assertIsNone(result["latency_ms"])
        self.assertEqual(result["reported_usage_totals"], {})
