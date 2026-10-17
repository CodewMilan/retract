from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import unittest

from retract.models import ConflictError, PlanInput, RememberInput, UpdateInput, parse
from retract.service import MemoryService
from tests.support import ModelStore
from tests.test_policy import confirmed_update


class ServiceTests(unittest.TestCase):
    """Application tests against a test model, not against FalkorDB."""

    def setUp(self):
        self.store = ModelStore()
        self.service = MemoryService(self.store)
        fixture = json.loads((Path(__file__).resolve().parents[1] / "fixtures/demo-seed.json").read_text())
        self.service.create_project(**fixture["project"])
        for action in fixture["actions"]:
            if action["route"] == "remember":
                self.service.remember(parse(RememberInput, action["body"]))
            else:
                self.plan = parse(PlanInput, action["body"])
                self.service.record_plan(self.plan)

    def test_demo_correction_and_proposal(self):
        untouched = {fact: self.store.get("Fact", "account-settings", fact) for fact in ("F2", "F3", "F4")}
        result = self.service.process_update(confirmed_update())
        self.assertEqual(result["retired_fact_ids"], ["F1"])
        self.assertEqual(result["accepted_fact_ids"], ["F5"])
        self.assertEqual(result["flagged_plan_ids"], ["P1"])
        self.assertEqual(result["explanation_paths"][0]["fact_id"], "F1")
        self.assertEqual(self.store.get("Fact", "account-settings", "F1")["status"], "superseded")
        for fact, original in untouched.items():
            self.assertEqual(self.store.get("Fact", "account-settings", fact), original)
        recalled = self.service.recall("account-settings", "web-client/main")
        self.assertEqual([fact["id"] for fact in recalled["active_facts"]], ["F5"])
        self.assertEqual(recalled["sources"][0]["source"]["id"], "S-U1")
        proposal = parse(UpdateInput, json.loads((Path(__file__).resolve().parents[1] / "fixtures/proposal.json").read_text()))
        self.assertEqual(self.service.process_update(proposal)["outcome"], "proposal")
        self.assertEqual(self.store.get("Fact", "account-settings", "F3"), untouched["F3"])

    def test_exact_replay_returns_original_result_without_side_effects(self):
        update = replace(confirmed_update(), expected_revision=5)
        result = self.service.process_update(update)
        snapshot = deepcopy(self.store.__dict__)
        self.assertEqual(self.service.process_update(update), result)
        self.assertEqual(self.store.__dict__, snapshot)

    def test_reused_event_id_with_changed_payload_is_rejected(self):
        self.service.process_update(confirmed_update())
        snapshot = deepcopy(self.store.__dict__)
        with self.assertRaises(ConflictError):
            self.service.process_update(replace(confirmed_update(), text="A different request"))
        self.assertEqual(self.store.__dict__, snapshot)

    def test_stale_revision_rejected_without_recording_event(self):
        snapshot = deepcopy(self.store.__dict__)
        with self.assertRaises(ConflictError):
            self.service.process_update(replace(confirmed_update(), expected_revision=0))
        self.assertEqual(self.store.__dict__, snapshot)

    def test_parallel_replays_are_serialized(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: self.service.process_update(confirmed_update()), range(16)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(self.service.project("account-settings")["revision"], 6)

    def test_ambiguous_event_keeps_accepted_state_and_exposes_pending(self):
        result = self.service.process_update(replace(confirmed_update(), classification="ambiguous"))
        self.assertEqual(result["outcome"], "pending")
        recalled = self.service.recall("account-settings", "web-client/main")
        self.assertEqual(recalled["active_facts"][0]["id"], "F1")
        self.assertEqual(recalled["pending_conflicts"][0]["event_id"], "U1")
        self.assertEqual(recalled["affected_plans"], [])

    def test_unlinked_plan_is_unchanged(self):
        self.service.record_plan(replace(self.plan, plan_id="P2", dependency_fact_ids=["F4"]))
        original = self.store.get("Plan", "account-settings", "P2")
        self.service.process_update(confirmed_update())
        self.assertEqual(self.store.get("Plan", "account-settings", "P2"), original)

    def test_remember_conflict_does_not_create_second_active_value(self):
        source = confirmed_update().source
        with self.assertRaises(ConflictError):
            self.service.remember(RememberInput("account-settings", "web-client/main", "browser-api", "authentication", "cookies", source))
        self.assertIsNone(self.store.get("Source", "account-settings", source.id))

    def test_duplicate_fact_adds_evidence_then_is_idempotent(self):
        request = RememberInput("account-settings", "web-client/main", "browser-api", "authentication", "bearer tokens", confirmed_update().source)
        self.assertEqual(self.service.remember(request)["fact_id"], "F1")
        self.assertEqual(len(self.store.sources("account-settings", ["F1"])), 2)
        snapshot = deepcopy(self.store.__dict__)
        self.service.remember(request)
        self.assertEqual(self.store.__dict__, snapshot)

    def test_source_ids_cannot_be_rewritten(self):
        update = confirmed_update()
        self.service.process_update(update)
        with self.assertRaises(ConflictError):
            self.service.process_update(replace(update, event_id="U3", source=replace(update.source, title="Changed evidence")))

    def test_project_isolation(self):
        self.service.create_project("other", "Other project")
        result = self.service.process_update(replace(confirmed_update(), project_id="other"))
        self.assertEqual(result["outcome"], "pending")
        self.assertEqual(self.service.recall("other", "web-client/main")["active_facts"], [])
        self.assertEqual(self.store.get("Fact", "account-settings", "F1")["status"], "active")

    def test_seeded_plan_replay_cannot_reset_needs_review(self):
        self.service.process_update(confirmed_update())
        result = self.service.record_plan(self.plan)
        self.assertEqual(result["status"], "needs_review")

    def test_plan_dependencies_must_exist_in_project(self):
        with self.assertRaises(ConflictError):
            self.service.record_plan(replace(self.plan, plan_id="P2", dependency_fact_ids=["unknown"]))

    def test_failure_before_repository_commit_can_retry_same_event(self):
        snapshot = deepcopy(self.store.__dict__)
        self.store.fail_next_write = True
        with self.assertRaises(RuntimeError):
            self.service.process_update(confirmed_update())
        self.assertEqual(self.store.__dict__, snapshot)
        self.assertEqual(self.service.process_update(confirmed_update())["outcome"], "applied")

    def test_event_history_includes_its_source(self):
        self.service.process_update(confirmed_update())
        history = self.service.history("account-settings", event_id="U1")
        self.assertEqual(history["source"]["id"], "S-U1")
        self.assertEqual(history["event"]["accepted_fact_ids"], ["F5"])
