from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import asdict, replace
from threading import Event, Thread
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from retract.inference import GroqInterpreter, ModelRateLimited, ModelResponseError, ModelUnavailable
from retract.models import ConflictError, PlanInput
from retract.service import MemoryService
from tests import test_http, test_service
from tests.test_inference import Transport, envelope, extracted, natural_request
from tests.test_policy import confirmed_update


class NaturalUpdateTests(unittest.TestCase):
    def setUp(self):
        test_service.ServiceTests.setUp(self)
        self.transport = Transport(envelope())
        self.service.interpreter = GroqInterpreter("test-key", opener=self.transport)

    def test_correction_uses_existing_policy_and_keeps_audit(self):
        unchanged = {fact: self.store.get("Fact", "account-settings", fact) for fact in ("F2", "F3", "F4")}
        result = self.service.process_natural_update(natural_request())
        self.assertEqual(result["outcome"], "applied")
        self.assertEqual(result["retired_fact_ids"], ["F1"])
        self.assertEqual(result["flagged_plan_ids"], ["P1"])
        self.assertEqual(len(result["accepted_fact_ids"]), 1)
        self.assertEqual(result["interpretation"]["prompt_version"], "retract-extract-v1")
        self.assertEqual(result["interpretation"]["usage"]["total_tokens"], 150)
        current = self.service.recall("account-settings", "web-client/main")["active_facts"]
        self.assertEqual([fact["value"] for fact in current], ["HTTP-only cookie sessions"])
        for fact, original in unchanged.items():
            self.assertEqual(self.store.get("Fact", "account-settings", fact), original)

    def test_exact_replay_avoids_model_and_survives_new_service_without_key(self):
        request = replace(natural_request(), expected_revision=5)
        result = self.service.process_natural_update(request)
        snapshot = deepcopy(self.store.__dict__)
        self.assertEqual(self.service.process_natural_update(request), result)
        fresh = MemoryService(self.store)
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}):
            self.assertEqual(fresh.process_natural_update(request), result)
        self.assertEqual(len(self.transport.requests), 1)
        self.assertEqual(self.store.__dict__, snapshot)

    def test_changed_request_or_structured_collision_is_rejected_before_model(self):
        self.service.process_natural_update(natural_request())
        with self.assertRaises(ConflictError):
            self.service.process_natural_update(replace(natural_request(), text="different request"))
        with self.assertRaises(ConflictError):
            self.service.process_update(replace(confirmed_update(), event_id=natural_request().event_id))
        self.assertEqual(len(self.transport.requests), 1)

    def test_explicit_confirmation_and_authority_are_required_after_extraction(self):
        for changes in ({"confirmation": False}, {"source": replace(natural_request().source, authority="untrusted")}):
            self.setUp()
            request = replace(natural_request(), **changes)
            result = self.service.process_natural_update(request)
            self.assertEqual(result["outcome"], "pending")
            self.assertEqual(self.store.get("Fact", "account-settings", "F1")["status"], "active")

    def test_proposal_ambiguity_and_unrelated_never_retire_facts(self):
        for classification, expected in (("proposal", "proposal"), ("ambiguous", "pending"), ("unrelated", "ignored")):
            self.setUp()
            self.service.interpreter = GroqInterpreter("test", opener=Transport(envelope(extracted(classification=classification))))
            result = self.service.process_natural_update(natural_request())
            self.assertEqual(result["outcome"], expected)
            self.assertEqual(result["retired_fact_ids"], [])
            self.assertEqual(self.store.get("Fact", "account-settings", "F1")["status"], "active")

    def test_model_scope_mismatch_is_recorded_as_pending(self):
        self.service.interpreter = GroqInterpreter("test", opener=Transport(envelope(extracted(scope="cli-client/main"))))
        result = self.service.process_natural_update(natural_request())
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(result["interpretation"]["extraction"]["scope"], "cli-client/main")
        self.assertEqual(self.store.get("Fact", "account-settings", "F1")["status"], "active")

    def test_missing_scoped_target_cannot_create_accepted_memory(self):
        self.service.create_project("other", "Other project")
        result = self.service.process_natural_update(replace(natural_request(), project_id="other"))
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(self.service.recall("other", "web-client/main")["active_facts"], [])
        self.assertEqual(self.store.get("Fact", "account-settings", "F1")["status"], "active")

    def test_invalid_output_or_provider_failure_records_no_event(self):
        for error in (ModelResponseError("invalid JSON"), ModelUnavailable("timeout"), ModelRateLimited(60)):
            self.service.interpreter = SimpleNamespace(extract=Mock(side_effect=error))
            snapshot = deepcopy(self.store.__dict__)
            with self.subTest(error=type(error).__name__), self.assertRaises(type(error)):
                self.service.process_natural_update(natural_request())
            self.assertEqual(self.store.__dict__, snapshot)

    def test_stale_client_revision_is_rejected_before_model_call(self):
        with self.assertRaises(ConflictError):
            self.service.process_natural_update(replace(natural_request(), expected_revision=0))
        self.assertEqual(self.transport.requests, [])

    def test_revision_changed_during_inference_cannot_apply_stale_extraction(self):
        interpreter = self.service.interpreter
        def extract_with_interleaved_write(request, current):
            self.service.record_plan(PlanInput("account-settings", "web-client/main", "Unrelated plan", [], plan_id="P2"))
            return interpreter.extract(request, current)
        self.service.interpreter = SimpleNamespace(extract=extract_with_interleaved_write)
        with self.assertRaises(ConflictError):
            self.service.process_natural_update(natural_request())
        self.assertIsNone(self.store.get("UpdateEvent", "account-settings", "N1"))
        self.assertEqual(self.store.get("Fact", "account-settings", "F1")["status"], "active")

    def test_network_wait_does_not_hold_application_lock(self):
        interpreter = self.service.interpreter
        def extract_with_other_thread(request, current):
            completed = Event()
            def recall():
                self.service.recall("account-settings", "cli-client/main")
                completed.set()
            worker = Thread(target=recall, daemon=True)
            worker.start()
            if not completed.wait(1):
                raise AssertionError("Inference held the service lock")
            worker.join(timeout=1)
            return interpreter.extract(request, current)
        self.service.interpreter = SimpleNamespace(extract=extract_with_other_thread)
        self.assertEqual(self.service.process_natural_update(natural_request())["outcome"], "applied")

    def test_source_conflict_is_rejected_before_inference(self):
        self.service.process_update(confirmed_update())
        request = replace(natural_request(), source=replace(natural_request().source, title="Modified source"))
        with self.assertRaises(ConflictError):
            self.service.process_natural_update(request)
        self.assertEqual(self.transport.requests, [])

    def test_http_natural_route_uses_the_same_application_policy(self):
        status, result, _ = test_http.HttpTests.request(self, "/updates/natural", asdict(natural_request()))
        self.assertEqual(status, 200)
        self.assertEqual(result["outcome"], "applied")

    def test_http_reports_model_errors_and_retry_after(self):
        for error, expected in ((ModelUnavailable("missing configuration"), 503), (ModelResponseError("bad output"), 502),
                                (ModelRateLimited(90), 429)):
            self.service.interpreter = SimpleNamespace(extract=Mock(side_effect=error))
            with self.subTest(error=type(error).__name__):
                status, result, headers = test_http.HttpTests.request(self, "/updates/natural", asdict(natural_request()))
                self.assertEqual(status, expected)
                if expected == 429:
                    self.assertIn("Retry-After: 90", headers)
                    self.assertEqual(result["retry_after_seconds"], 90)
                self.assertEqual(self.service.project("account-settings")["revision"], 5)

    def test_simultaneous_nondeterministic_replays_commit_only_one_result(self):
        from threading import Barrier
        barrier = Barrier(2)
        second = extracted()
        second["candidate"]["value"] = "cookie sessions"
        transport = Transport(envelope(), envelope(second))
        provider = GroqInterpreter("test", opener=transport)
        def extract(request, current):
            barrier.wait(timeout=2)
            return provider.extract(request, current)
        self.service.interpreter = SimpleNamespace(extract=extract)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.service.process_natural_update(natural_request()), range(2)))
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.service.project("account-settings")["revision"], 6)
        self.assertEqual(len(self.service.recall("account-settings", "web-client/main")["active_facts"]), 1)
