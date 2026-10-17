"""Opt-in tests against an actual, disposable FalkorDB graph.

RUN_FALKORDB_TESTS=1 PYTHONPATH=src python -m unittest tests.test_integration -v
Never deletes the configured application graph; each test owns a UUID graph.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import os
from pathlib import Path
import unittest
from uuid import uuid4

from retract.graph import GraphStore, DatabaseUnavailable
from retract.models import ConflictError, PlanInput, RememberInput, UpdateInput, parse
from retract.service import MemoryService
from tests.test_policy import confirmed_update


@unittest.skipUnless(os.getenv("RUN_FALKORDB_TESTS") == "1", "Requires real FalkorDB; set RUN_FALKORDB_TESTS=1")
class FalkorDBTests(unittest.TestCase):
    def setUp(self):
        from falkordb import FalkorDB

        self.client = FalkorDB(host=os.getenv("FALKORDB_HOST", "127.0.0.1"),
                              port=int(os.getenv("FALKORDB_PORT", "6380")),
                              password=os.getenv("FALKORDB_PASSWORD") or None,
                              socket_timeout=10, socket_connect_timeout=3)
        self.graph_name = f"retract-test-{uuid4().hex}"
        self.graph = self.client.select_graph(self.graph_name)
        self.store = GraphStore(self.graph)
        self.store.initialize()
        self.addCleanup(self.client.connection.close)
        self.addCleanup(self.graph.delete)
        self.service = MemoryService(self.store)
        fixture = json.loads((Path(__file__).resolve().parents[1] / "fixtures/demo-seed.json").read_text())
        self.service.create_project(**fixture["project"])
        self.seed_fact = parse(RememberInput, fixture["actions"][0]["body"])
        self.plan = parse(PlanInput, fixture["actions"][-1]["body"])
        for action in fixture["actions"]:
            if action["route"] == "remember":
                self.service.remember(parse(RememberInput, action["body"]))
            else:
                self.service.record_plan(parse(PlanInput, action["body"]))

    def test_graph_correction_history_and_impact(self):
        before = {fact: self.store.get("Fact", "account-settings", fact) for fact in ("F2", "F3", "F4")}
        result = self.service.process_update(confirmed_update())
        self.assertEqual(result["retired_fact_ids"], ["F1"])
        self.assertEqual(result["accepted_fact_ids"], ["F5"])
        self.assertEqual(result["flagged_plan_ids"], ["P1"])
        recall = self.service.recall("account-settings", "web-client/main")
        self.assertEqual([fact["id"] for fact in recall["active_facts"]], ["F5"])
        self.assertEqual(recall["affected_plans"][0]["explanation_paths"][0]["fact_id"], "F1")
        history = self.service.history("account-settings", fact_id="F1")
        self.assertEqual({fact["id"] for fact in history["facts"]}, {"F1", "F5"})
        self.assertEqual(history["replacement_links"], [{"new_fact_id": "F5", "old_fact_id": "F1"}])
        self.assertEqual({link["source"]["id"] for link in history["sources"]}, {"S-F1", "S-U1"})
        self.assertEqual(history["events"][0]["event_id"], "U1")
        for fact, original in before.items():
            self.assertEqual(self.store.get("Fact", "account-settings", fact), original)

    def test_proposals_ambiguity_and_untrusted_updates_preserve_accepted_facts(self):
        for index, changes in enumerate(({"classification": "proposal"}, {"classification": "ambiguous"},
                                         {"confirmation": False},
                                         {"source": replace(confirmed_update().source, authority="untrusted")})):
            update = replace(confirmed_update(), event_id=f"event-{index}", **changes)
            update = replace(update, source=replace(update.source, id=f"source-{index}"))
            self.service.process_update(update)
        recall = self.service.recall("account-settings", "web-client/main")
        self.assertEqual([fact["id"] for fact in recall["active_facts"]], ["F1"])
        self.assertEqual(len(recall["pending_conflicts"]), 3)
        self.assertEqual(recall["affected_plans"], [])

    def test_replay_is_exact_and_idempotent_under_threads(self):
        update = replace(confirmed_update(), expected_revision=5)
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(lambda _: self.service.process_update(update), range(12)))
        self.assertTrue(all(result == results[0] for result in results))
        self.assertEqual(self.service.project("account-settings")["revision"], 6)
        self.assertEqual(self.store.query("MATCH (e:UpdateEvent) RETURN count(e)", {})[0][0], 1)
        with self.assertRaises(ConflictError):
            self.service.process_update(replace(update, text="Different event"))

    def test_different_scope_and_project_are_isolated(self):
        self.service.create_project("other", "Other")
        self.assertEqual(self.service.process_update(replace(confirmed_update(), project_id="other"))["outcome"], "pending")
        self.assertEqual(self.service.process_update(replace(confirmed_update(), scope="cli-client/main"))["outcome"], "pending")
        self.assertEqual(self.service.recall("other", "web-client/main")["active_facts"], [])
        self.assertEqual(self.store.get("Fact", "account-settings", "F1")["status"], "active")

    def test_duplicate_evidence_conflicts_and_immutable_sources(self):
        self.assertEqual(self.service.remember(self.seed_fact)["outcome"], "duplicate")
        self.assertEqual(self.service.project("account-settings")["revision"], 5)
        self.service.remember(replace(self.seed_fact, source=replace(self.seed_fact.source, id="another-source")))
        self.assertEqual(len(self.store.sources("account-settings", ["F1"])), 2)
        with self.assertRaises(ConflictError):
            self.service.remember(replace(self.seed_fact, value="cookies"))
        with self.assertRaises(ConflictError):
            self.service.remember(replace(self.seed_fact, source=replace(self.seed_fact.source, content="changed")))

    def test_zero_dependency_plan_and_plan_replay(self):
        self.service.record_plan(replace(self.plan, plan_id="P2", dependency_fact_ids=[]))
        self.assertEqual(self.store.plan_dependencies("account-settings", "P2"), [])
        self.service.process_update(confirmed_update())
        self.assertEqual(self.store.get("Plan", "account-settings", "P2")["status"], "current")
        self.assertEqual(self.service.record_plan(self.plan)["status"], "needs_review")

    def test_new_service_instance_reads_same_ids_and_history_without_reseeding(self):
        self.service.process_update(confirmed_update())
        before = self.service.recall("account-settings", "web-client/main")
        history = self.service.history("account-settings", fact_id="F1")
        # A fresh graph object/service, not a simulated database restart.
        fresh = MemoryService(GraphStore(self.client.select_graph(self.graph_name)))
        self.assertEqual(fresh.recall("account-settings", "web-client/main"), before)
        self.assertEqual(fresh.history("account-settings", fact_id="F1"), history)

    def test_revision_guard_and_invalid_query_leave_state_unchanged(self):
        before = self.service.recall("account-settings", "web-client/main")
        with self.assertRaises(ConflictError):
            self.service.process_update(replace(confirmed_update(), expected_revision=0))
        with self.assertRaises(ConflictError):
            self.store.record_event("account-settings", 0,
                                    {"id": "stale-source", "project_id": "account-settings"},
                                    {"id": "stale-event", "project_id": "account-settings"}, None, None)
        with self.assertRaises(DatabaseUnavailable):
            self.store.query("THIS IS INVALID CYPHER", {}, write=True)
        self.assertEqual(self.service.recall("account-settings", "web-client/main"), before)

    def test_http_adapter_uses_the_same_service_and_reports_errors(self):
        from threading import Thread
        from urllib.error import HTTPError
        from urllib.request import Request, urlopen

        from retract.api import make_server
        from retract.cli import call

        server = make_server(self.service, 0)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(f"{base}/health", timeout=5) as response:
                self.assertEqual(json.load(response)["storage"], "falkordb")
            from dataclasses import asdict
            result = call(base, "updates", asdict(confirmed_update()))
            self.assertEqual(result["outcome"], "applied")
            self.assertEqual(call(base, "recall", {"project_id": "account-settings", "scope": "web-client/main"})["active_facts"][0]["id"], "F5")
            with self.assertRaises(RuntimeError):
                call(base, "remember", {})
            request = Request(f"{base}/updates", data=b"{}", headers={
                "Content-Type": "application/json", "Origin": "https://example.com"})
            with self.assertRaises(HTTPError) as raised:
                urlopen(request, timeout=5)
            self.assertEqual(raised.exception.code, 403)
            raised.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_runtime_failure_rolls_back_the_complete_correction_query(self):
        from unittest.mock import patch

        before = self.service.recall("account-settings", "web-client/main")
        counts = self.store.query("MATCH (n) RETURN count(n)", {})
        original = self.store.query

        def fail_after_transition(statement, params, *, write=False):
            if write and "CREATE (e:UpdateEvent)" in statement:
                statement = statement.replace(
                    "RETURN p.revision",
                    "WITH p UNWIND [1, 0] AS divisor "
                    "CREATE (:FailureProbe {value: 1 / divisor}) RETURN p.revision",
                )
            return original(statement, params, write=write)

        # Inject a runtime error after the real correction clauses, not before commit.
        with patch.object(self.store, "query", side_effect=fail_after_transition):
            with self.assertRaises(DatabaseUnavailable):
                self.service.process_update(confirmed_update())
        self.assertEqual(self.service.recall("account-settings", "web-client/main"), before)
        self.assertEqual(self.store.query("MATCH (n) RETURN count(n)", {}), counts)
        self.assertIsNone(self.store.get("UpdateEvent", "account-settings", "U1"))
        self.assertIsNone(self.store.get("Fact", "account-settings", "F5"))
        self.assertIsNone(self.store.get("Source", "account-settings", "S-U1"))
        self.assertEqual(self.service.process_update(confirmed_update())["outcome"], "applied")
