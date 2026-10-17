"""Test-only repository model. This does not test Cypher or database durability."""

from copy import deepcopy
import json

from retract.models import ConflictError


class ModelStore:
    def __init__(self):
        self.nodes = {}
        self.supports = set()
        self.dependencies = set()
        self.replacements = set()
        self.flagged = set()
        self.fail_next_write = False

    def get(self, label, project, node_id):
        node = self.nodes.get((label, project, node_id))
        return deepcopy(node)

    def put(self, label, node):
        self.nodes[(label, node["project_id"], node["id"])] = deepcopy(node)

    def create_project(self, project, name):
        node = {"id": project, "project_id": project, "name": name, "revision": 0}
        self.put("Project", node)
        return node

    def _write(self, project, expected):
        if self.fail_next_write:
            self.fail_next_write = False
            raise RuntimeError("Injected repository failure before commit")
        node = self.get("Project", project, project)
        if node["revision"] != expected:
            raise ConflictError("Stale revision")
        node["revision"] += 1
        self.put("Project", node)

    def active(self, project, scope, subject, predicate):
        for (label, owner, _), node in self.nodes.items():
            if label == "Fact" and owner == project and node["scope"] == scope and node["subject"] == subject and node["predicate"] == predicate and node["status"] == "active":
                return deepcopy(node)
        return None

    def remember(self, project, revision, source, fact):
        self._write(project, revision)
        self.put("Fact", fact)
        self.put("Source", source)
        self.supports.add((project, source["id"], fact["id"]))

    def sources(self, project, ids):
        return [{"source": self.get("Source", owner, source), "fact_id": fact}
                for owner, source, fact in sorted(self.supports) if owner == project and fact in ids]

    def attach_source(self, project, revision, source, fact_id):
        self._write(project, revision)
        self.put("Source", source)
        self.supports.add((project, source["id"], fact_id))

    def record_plan(self, project, revision, plan, ids):
        self._write(project, revision)
        self.put("Plan", plan)
        self.dependencies.update((project, plan["id"], fact) for fact in ids)

    def plan_dependencies(self, project, plan_id):
        return sorted(fact for owner, plan, fact in self.dependencies if owner == project and plan == plan_id)

    def dependent_paths(self, project, fact_id):
        return [{"plan_id": plan, "fact_id": fact, "relationship": "DEPENDS_ON"}
                for owner, plan, fact in sorted(self.dependencies) if owner == project and fact == fact_id]

    def record_event(self, project, revision, source, event, new_fact, target_id):
        self._write(project, revision)
        self.put("Source", source)
        self.put("UpdateEvent", event)
        if new_fact:
            old = self.get("Fact", project, target_id)
            old.update(status="superseded", superseded_at=event["recorded_at"])
            self.put("Fact", old)
            self.put("Fact", new_fact)
            self.supports.add((project, source["id"], new_fact["id"]))
            self.replacements.add((project, new_fact["id"], target_id))
            for path in self.dependent_paths(project, target_id):
                plan = self.get("Plan", project, path["plan_id"])
                plan["status"] = "needs_review"
                self.put("Plan", plan)
                self.flagged.add((project, event["id"], plan["id"]))

    def recall(self, project, scope, subjects):
        facts = [deepcopy(node) for (label, owner, _), node in self.nodes.items()
                 if label == "Fact" and owner == project and node["scope"] == scope
                 and node["status"] == "active" and (not subjects or node["subject"] in subjects)]
        plans = [deepcopy(node) for (label, owner, _), node in self.nodes.items()
                 if label == "Plan" and owner == project and node["scope"] == scope and node["status"] == "needs_review"]
        pending = [json.loads(node["result_json"]) for (label, owner, _), node in self.nodes.items()
                   if label == "UpdateEvent" and owner == project and node["scope"] == scope and node["outcome"] == "pending"]
        return {"active_facts": facts, "sources": self.sources(project, [node["id"] for node in facts]),
                "affected_plans": [{"plan": plan} for plan in plans], "pending_conflicts": pending}
