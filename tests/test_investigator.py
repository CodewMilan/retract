import json
import os
import unittest

from retract.analysis import GraphAnalysis
from retract.api import dispatch
from retract.inference import GroqInterpreter
from retract.investigator import GroqPlanner, InvestigatorAgent, PlaybookPlanner
from retract.mcp_tools import ApiError
from retract.models import ConflictError, NotFoundError, ValidationError
from tests import test_integration, test_service
from tests.test_inference import Transport, envelope, http_error
from tests.test_policy import confirmed_update

PROJECT = "account-settings"
BLANK = {"node_id": None, "target_id": None, "algorithm": None, "depth": None, "finding_id": None, "note": None}


def step(action, **values):
    return {**BLANK, "reasoning": f"test step {action}", "action": action, **values}


class Scripted:
    label = "scripted"

    def __init__(self, *decisions):
        self.decisions = list(decisions)
        self.states = []

    def decide(self, state):
        self.states.append(state)
        return self.decisions.pop(0)


class AnalysisWithoutFalkorDB(unittest.TestCase):
    setUp = test_service.ServiceTests.setUp

    def test_analysis_requires_the_real_graph_store(self):
        with self.assertRaises(ValidationError):
            dispatch(self.service, "/analyze", {"project_id": PROJECT, "tool": "findings"})


class PlannerTransportTests(unittest.TestCase):
    def test_groq_planner_sends_strict_schema_and_waits_out_rate_limits(self):
        decision = step("findings")
        slept = []
        transport = Transport(http_error(429, "5"), envelope(decision))
        planner = GroqPlanner(GroqInterpreter("test", opener=transport), sleep=slept.append)
        self.assertEqual(planner.decide({"notebook": []})["action"], "findings")
        body = json.loads(transport.requests[-1][0].data)
        self.assertTrue(body["response_format"]["json_schema"]["strict"])
        self.assertEqual(slept, [6])
        self.assertEqual(planner.audit[0]["model"], "openai/gpt-oss-20b")


@unittest.skipUnless(os.getenv("RUN_FALKORDB_TESTS") == "1", "Requires real FalkorDB")
class InvestigationGraphTests(unittest.TestCase):
    setUp = test_integration.FalkorDBTests.setUp

    def api(self, route, body):
        self.calls.append(route)
        try:
            return dispatch(self.service, route, body)
        except ConflictError as exc:
            raise ApiError(str(exc), 409) from None
        except NotFoundError as exc:
            raise ApiError(str(exc), 404) from None
        except ValidationError as exc:
            raise ApiError(str(exc), 400) from None

    def analyze(self, tool, **args):
        return dispatch(self.service, "/analyze", {"project_id": PROJECT, "tool": tool, "args": args})

    def agent(self, planner):
        self.calls = []
        return InvestigatorAgent(self.api, planner, max_steps=12)

    def test_no_findings_before_a_correction(self):
        self.assertEqual(self.analyze("findings")["findings"], [])

    def test_detectors_and_algorithms_explain_the_correction(self):
        self.service.process_update(confirmed_update())
        findings = {f["id"]: f for f in self.analyze("findings")["findings"]}
        self.assertEqual(set(findings), {"stale_plan:P1", "cross_scope_drift:F2:U1"})
        self.assertEqual(findings["stale_plan:P1"]["current_fact_ids"], ["F4", "F5"])
        self.assertEqual(findings["stale_plan:P1"]["evidence"], [{"fact_id": "F1", "current_fact_id": "F5"}])
        drift = findings["cross_scope_drift:F2:U1"]
        self.assertEqual((drift["scope"], drift["dependent_plan_ids"], drift["severity"]), ("cli-client/main", [], "low"))

        radius = self.analyze("blast_radius", node_id="F1", depth=2)
        self.assertEqual(radius["reached_by_label"]["Plan"], ["P1"])
        self.assertIn("U1", radius["reached_by_label"]["UpdateEvent"])
        self.assertNotIn("F2", radius["reached_by_label"]["Fact"])
        plan = next(item for item in radius["reached"] if item["id"] == "P1")
        self.assertEqual(plan["path"], [{"type": "DEPENDS_ON", "from": "P1", "to": "F1"}])

        path = self.analyze("trace", from_id="F5", to_id="P1")
        self.assertEqual((path["connected"], path["hops"]), (True, 2))
        self.assertFalse(self.analyze("trace", from_id="F2", to_id="P1")["connected"])

        ranked = self.analyze("centrality")["ranked"]
        self.assertEqual({r["id"] for r in ranked}, {"F1", "F2", "F3", "F4", "F5"})
        self.assertEqual(next(r for r in ranked if r["id"] == "F4")["dependent_plan_ids"], ["P1"])
        components = self.analyze("components")
        self.assertEqual(components["facts_without_any_plan_in_component"], ["F2", "F3"])

    def test_bad_arguments_are_rejected(self):
        for tool, args in [("drop", {}), ("blast_radius", {"node_id": "F1", "depth": 9}),
                           ("centrality", {"algorithm": "louvain"}), ("overview", {"scope": "x"})]:
            with self.subTest(tool=tool), self.assertRaises(ValidationError):
                self.analyze(tool, **args)
        with self.assertRaises(NotFoundError):
            self.analyze("blast_radius", node_id="missing")

    def test_playbook_investigation_hands_off_once_and_reports_leads(self):
        self.service.process_update(confirmed_update())
        report = self.agent(PlaybookPlanner()).run(PROJECT)
        self.assertEqual([a["plan_id"] for a in report["actions"]], ["P1"])
        self.assertIn("F2", report["report"])
        [handoff] = self.service.recall(PROJECT, "web-client/main")["open_handoffs"]
        self.assertEqual((handoff["handoff"]["from_agent"], handoff["handoff"]["to_agent"]),
                         ("retract-investigator", "codex"))
        self.assertIn("(P1)-[:DEPENDS_ON]->(F1)", handoff["handoff"]["note"])
        self.assertEqual(self.store.get("Fact", PROJECT, "F2")["status"], "active")
        self.assertEqual(self.store.get("Plan", PROJECT, "P1")["status"], "needs_review")

        rerun = self.agent(Scripted(step("findings"), step("blast_radius", node_id="P1"),
                                    step("handoff", finding_id="stale_plan:P1"), step("finish", note="done"))).run(PROJECT)
        self.assertEqual(rerun["actions"], [])
        self.assertIn("already has a open handoff", rerun["steps"][2]["observation"])
        self.assertNotIn("/handoffs", self.calls)

    def test_guards_reject_unsafe_or_unsupported_actions(self):
        self.service.process_update(confirmed_update())
        planner = Scripted(step("findings"), step("findings"),
                           step("handoff", finding_id="stale_plan:P1"),
                           step("handoff", finding_id="invented:P9"),
                           step("blast_radius", node_id="F2"),
                           step("handoff", finding_id="cross_scope_drift:F2:U1"),
                           step("trace", node_id="F2", target_id="nope"),
                           step("finish", note="Reported F2 drift."))
        report = self.agent(planner).run(PROJECT)
        observations = [s["observation"] for s in report["steps"]]
        self.assertIn("Already ran this exact step", observations[1])
        self.assertIn("inspect P1", observations[2])
        self.assertIn("does not name a finding", observations[3])
        self.assertIn("no live plan", observations[5])
        self.assertTrue(observations[6].startswith("error:"))
        self.assertEqual(report["actions"], [])
        self.assertEqual(self.calls.count("/analyze"), 3)
        self.assertNotIn("/handoffs", self.calls)
        self.assertEqual(report["report"], "Reported F2 drift.")
