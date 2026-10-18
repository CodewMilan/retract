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

    def revise_plan(self, project, revision, previous_id, plan, ids):
        self._write(project, revision)
        previous = self.get("Plan", project, previous_id)
        previous.update(status="superseded", superseded_at=plan["recorded_at"])
        self.put("Plan", previous)
        self.put("Plan", plan)
        self.dependencies.update((project, plan["id"], fact) for fact in ids)

    def create_handoff(self, project, revision, handoff, fact_ids):
        self._write(project, revision)
        self.put("Handoff", handoff)
        self.cites = getattr(self, "cites", set()) | {(project, handoff["id"], fact) for fact in fact_ids}

    def claim_handoff(self, project, revision, handoff_id, agent, claimed_at):
        handoff = self.get("Handoff", project, handoff_id)
        if handoff["status"] != "open":
            raise ConflictError("Handoff already claimed")
        self._write(project, revision)
        handoff.update(status="claimed", claimed_by=agent, claimed_at=claimed_at)
        self.put("Handoff", handoff)

    def open_handoffs(self, project, scope):
        return sorted([deepcopy(n) for (label, owner, _), n in self.nodes.items()
                       if label == "Handoff" and owner == project and n["scope"] == scope and n["status"] == "open"],
                      key=lambda n: (n["recorded_at"], n["id"]))

    def handoff_fact_ids(self, project, handoff_id):
        return sorted(fact for owner, handoff, fact in getattr(self, "cites", set())
                      if owner == project and handoff == handoff_id)

    def current_plan(self, project, plan_id):
        plan = self.get("Plan", project, plan_id)
        while plan and plan["status"] == "superseded":
            plan = next((deepcopy(n) for (label, owner, _), n in self.nodes.items() if label == "Plan"
                         and owner == project and n.get("supersedes_plan_id") == plan["id"]), None)
        return {"plan_id": plan["id"], "status": plan["status"]} if plan else None

    def current_fact(self, project, fact_id):
        fact = self.get("Fact", project, fact_id)
        while fact and fact["status"] != "active":
            newer = next((new for owner, new, old in self.replacements if owner == project and old == fact["id"]), None)
            fact = self.get("Fact", project, newer) if newer else None
        return fact["id"] if fact else None

    def dependent_paths(self, project, fact_id):
        return [{"plan_id": plan, "fact_id": fact, "relationship": "DEPENDS_ON"}
                for owner, plan, fact in sorted(self.dependencies) if owner == project and fact == fact_id
                and self.get("Plan", project, plan)["status"] != "superseded"]

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

    def list_projects(self):
        projects = sorted([deepcopy(n) for (label, _, _), n in self.nodes.items() if label == 'Project'], key=lambda n: (n['name'], n['id']))
        return {'projects': projects[:100], 'truncated': len(projects) > 100}

    def dashboard_snapshot(self, project, scope=None):
        def all_nodes(label):
            return [deepcopy(n) for (kind, owner, _), n in self.nodes.items() if kind == label and owner == project]

        truncated, counts = {}, {}

        def panel(label, predicate, key):
            nodes = sorted([n for n in all_nodes(label) if (scope is None or n.get('scope') == scope) and predicate(n)],
                           key=lambda n: (n.get('recorded_at', ''), n['id']), reverse=True)
            counts[key], truncated[key] = len(nodes), len(nodes) > 200
            return nodes[:200]

        facts = panel('Fact', lambda n: n['status'] == 'active', 'active') + panel('Fact', lambda n: n['status'] == 'superseded', 'superseded')
        affected = panel('Plan', lambda n: n['status'] == 'needs_review', 'affected')
        plans = panel('Plan', lambda n: True, 'plans')
        plans = list({n['id']: n for n in plans + affected}.values())
        for plan in plans:
            plan.pop('review_fingerprint', None)
            plan.pop('review_result_json', None)
        pending = panel('UpdateEvent', lambda n: n['outcome'] in ('pending', 'proposal'), 'pending')
        recent = panel('UpdateEvent', lambda n: True, 'updates')
        updates = list({n['id']: n for n in recent + pending}.values())
        scopes = sorted({n['scope'] for label in ('Fact', 'Plan', 'UpdateEvent') for n in all_nodes(label)})
        edges, paths = [], []

        def edge(kind, left_label, left, right_label, right):
            def clean(label, node_id):
                return {k: v for k, v in self.get(label, project, node_id).items() if k not in ('fingerprint', 'result_json', 'review_fingerprint', 'review_result_json')}
            edges.append({'relationship': kind, 'from': clean(left_label, left), 'to': clean(right_label, right)})

        for owner, source, fact in sorted(self.supports):
            if owner == project and any(n['id'] == fact for n in facts):
                edge('SUPPORTS', 'Source', source, 'Fact', fact)
        for owner, newer, older in sorted(self.replacements):
            if owner == project and any(n['id'] == newer for n in facts):
                edge('SUPERSEDES', 'Fact', newer, 'Fact', older)
        for owner, plan, fact in sorted(self.dependencies):
            if owner == project and any(n['id'] == plan for n in plans):
                edge('DEPENDS_ON', 'Plan', plan, 'Fact', fact)
        for plan in plans:
            if plan.get('supersedes_plan_id'):
                edge('REVISES', 'Plan', plan['id'], 'Plan', plan['supersedes_plan_id'])
        for event in updates:
            result = json.loads(event['result_json'])
            edge('BASED_ON', 'UpdateEvent', event['id'], 'Source', result['source_id'])
            for kind, key, label in [('RETIRED', 'retired_fact_ids', 'Fact'), ('ACCEPTED', 'accepted_fact_ids', 'Fact'), ('FLAGGED', 'flagged_plan_ids', 'Plan')]:
                for target in result[key]:
                    edge(kind, 'UpdateEvent', event['id'], label, target)
        for owner, event_id, plan in sorted(self.flagged):
            if owner != project or not any(n['id'] == plan for n in plans):
                continue
            event = self.get('UpdateEvent', project, event_id)
            result = json.loads(event.pop('result_json'))
            event.pop('fingerprint')
            for fact in result['retired_fact_ids']:
                if (project, plan, fact) in self.dependencies:
                    paths.append({'event': event, 'plan': self.get('Plan', project, plan), 'fact': self.get('Fact', project, fact)})
        truncated.update(edges=len(edges) > 1000, scopes=len(scopes) > 200, explanation_paths=len(paths) > 1000)
        return {'facts': facts, 'plans': plans, 'updates': updates, 'counts': counts, 'scopes': scopes[:200],
                'edges': edges[:1000], 'explanation_paths': paths[:1000], 'truncated': truncated}
