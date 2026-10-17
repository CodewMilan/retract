from copy import deepcopy
import unittest

from scripts.verify_phase1 import GateFailure, assert_demo_state


def valid_snapshot():
    def recall(facts, plans=None):
        return {"active_facts": [{"id": fact_id, "value": value, "status": "active"} for fact_id, value in facts],
                "affected_plans": plans or [], "project_revision": 7}

    result = {
        "web": recall([("F5", "HTTP-only cookie sessions")], [{
            "plan": {"id": "P1", "status": "needs_review"},
            "explanation_paths": [{"event_id": "U1", "fact_id": "F1", "plan_id": "P1"}],
        }]),
        "cli": recall([("F2", "bearer tokens")]),
        "account": recall([("F3", "PostgreSQL"), ("F4", "own profile only")]),
        "history": {"facts": [{"id": "F1", "status": "superseded"}, {"id": "F5", "status": "active"}],
                    "replacement_links": [{"new_fact_id": "F5", "old_fact_id": "F1"}],
                    "sources": [{"source": {"id": "S-F1"}}, {"source": {"id": "S-U1"}}],
                    "project_revision": 7},
        "correction": {"event": {"outcome": "applied"}, "project_revision": 7},
        "proposal": {"event": {"outcome": "proposal", "accepted_fact_ids": []}, "project_revision": 7},
    }
    return result


class VerificationTests(unittest.TestCase):
    def test_declared_fixture_state_passes_acceptance(self):
        assert_demo_state(valid_snapshot())

    def test_stale_current_context_cannot_pass(self):
        state = valid_snapshot()
        state["web"]["active_facts"].append({"id": "F1", "value": "bearer tokens", "status": "active"})
        with self.assertRaisesRegex(GateFailure, "Web recall"):
            assert_demo_state(state)

    def test_unrelated_mutations_cannot_pass(self):
        original = valid_snapshot()
        for key in ("cli", "account"):
            state = deepcopy(original)
            state[key]["active_facts"][0]["value"] = "unexpected replacement"
            with self.subTest(scope=key), self.assertRaises(GateFailure):
                assert_demo_state(state)

    def test_lost_history_or_evidence_cannot_pass(self):
        for key in ("facts", "replacement_links", "sources"):
            state = valid_snapshot()
            state["history"][key] = []
            with self.subTest(key=key), self.assertRaises(GateFailure):
                assert_demo_state(state)

    def test_missing_dependency_explanation_cannot_pass(self):
        state = valid_snapshot()
        state["web"]["affected_plans"][0]["explanation_paths"] = []
        with self.assertRaisesRegex(GateFailure, "dependency explanation"):
            assert_demo_state(state)

    def test_proposal_mutation_or_reseed_revision_cannot_pass(self):
        state = valid_snapshot()
        state["proposal"]["event"]["accepted_fact_ids"] = ["wrong"]
        with self.assertRaisesRegex(GateFailure, "Proposal accepted"):
            assert_demo_state(state)
        state = valid_snapshot()
        state["web"]["project_revision"] = 5
        with self.assertRaisesRegex(GateFailure, "revision"):
            assert_demo_state(state)
