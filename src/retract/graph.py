"""FalkorDB persistence. Values are parameters; only trusted labels form query text.

Every state transition is one graph write, guarded by the project revision. The
application serializes reads plus writes in one service process. No distributed
writer or generic transaction rollback guarantee is claimed.
"""

import os

from .models import ConflictError


class DatabaseUnavailable(RuntimeError):
    pass


class GraphStore:
    def __init__(self, graph=None):
        self.client = None
        if graph is None:
            from falkordb import FalkorDB

            self.client = FalkorDB(
                host=os.getenv("FALKORDB_HOST", "127.0.0.1"),
                port=int(os.getenv("FALKORDB_PORT", "6380")),
                password=os.getenv("FALKORDB_PASSWORD") or None,
                socket_timeout=10,
                socket_connect_timeout=3,
            )
            graph = self.client.select_graph(os.getenv("FALKORDB_GRAPH", "retract"))
        self.graph = graph

    def initialize(self):
        # GRAPH.RO_QUERY cannot read a graph that has never been created.
        self.query("RETURN 1", {}, write=True)

    def close(self):
        if self.client:
            self.client.connection.close()

    def query(self, statement: str, params: dict, *, write: bool = False) -> list:
        try:
            method = self.graph.query if write else self.graph.ro_query
            return method(statement, params).result_set
        except Exception as exc:
            # Do not leak connection strings or source material through API errors.
            raise DatabaseUnavailable("FalkorDB query failed; inspect server logs and connectivity") from exc

    def get(self, label: str, project_id: str, node_id: str) -> dict | None:
        if label not in {"Project", "Source", "Fact", "Plan", "UpdateEvent", "Handoff"}:
            raise ValueError("Unsupported internal node label")
        rows = self.query(
            f"MATCH (n:{label} {{project_id: $project, id: $id}}) RETURN properties(n)",
            {"project": project_id, "id": node_id},
        )
        if len(rows) > 1:
            raise ConflictError("Duplicate stored IDs; graph needs review")
        return dict(rows[0][0]) if rows else None

    def create_project(self, project_id: str, name: str) -> dict:
        rows = self.query(
            "MERGE (p:Project {id: $id, project_id: $id}) "
            "ON CREATE SET p.name = $name, p.revision = 0 RETURN properties(p)",
            {"id": project_id, "name": name}, write=True,
        )
        return dict(rows[0][0])

    def active(self, project: str, scope: str, subject: str, predicate: str) -> dict | None:
        rows = self.query(
            "MATCH (f:Fact {project_id: $project, scope: $scope, subject: $subject, "
            "predicate: $predicate, status: 'active'}) RETURN properties(f)",
            {"project": project, "scope": scope, "subject": subject, "predicate": predicate},
        )
        if len(rows) > 1:
            raise ConflictError("Multiple active values for one key; graph needs review")
        return dict(rows[0][0]) if rows else None

    def dependent_paths(self, project: str, fact_id: str) -> list[dict]:
        rows = self.query(
            "MATCH (p:Plan {project_id: $project})-[:DEPENDS_ON]->"
            "(f:Fact {project_id: $project, id: $fact}) "
            "WHERE p.status <> 'superseded' RETURN p.id, f.id ORDER BY p.id",
            {"project": project, "fact": fact_id},
        )
        return [{"plan_id": row[0], "fact_id": row[1], "relationship": "DEPENDS_ON"} for row in rows]

    def plan_dependencies(self, project: str, plan_id: str) -> list[str]:
        rows = self.query(
            "MATCH (p:Plan {project_id: $project, id: $plan})-[:DEPENDS_ON]->"
            "(f:Fact {project_id: $project}) RETURN f.id ORDER BY f.id",
            {"project": project, "plan": plan_id},
        )
        return [row[0] for row in rows]

    def _write(self, statement: str, params: dict):
        rows = self.query(statement, params, write=True)
        if not rows:
            raise ConflictError("Project revision changed; retrieve context and retry")

    def remember(self, project: str, expected: int, source: dict, fact: dict):
        self._write(
            "MATCH (p:Project {id: $project, project_id: $project}) "
            "WHERE p.revision = $revision "
            "MERGE (s:Source {id: $source.id, project_id: $project}) ON CREATE SET s = $source "
            "CREATE (f:Fact) SET f = $fact "
            "CREATE (p)-[:HAS_FACT]->(f), (s)-[:SUPPORTS]->(f) "
            "SET p.revision = $revision + 1 RETURN p.revision",
            {"project": project, "revision": expected, "source": source, "fact": fact},
        )

    def attach_source(self, project: str, expected: int, source: dict, fact_id: str):
        self._write(
            "MATCH (p:Project {id: $project, project_id: $project}), "
            "(f:Fact {id: $fact, project_id: $project}) WHERE p.revision = $revision "
            "MERGE (s:Source {id: $source.id, project_id: $project}) ON CREATE SET s = $source "
            "MERGE (s)-[:SUPPORTS]->(f) SET p.revision = $revision + 1 RETURN p.revision",
            {"project": project, "revision": expected, "source": source, "fact": fact_id},
        )

    def sources(self, project: str, fact_ids: list[str]) -> list[dict]:
        rows = self.query(
            "MATCH (s:Source {project_id: $project})-[:SUPPORTS]->"
            "(f:Fact {project_id: $project}) WHERE f.id IN $ids "
            "RETURN s.id, properties(s), f.id ORDER BY s.id, f.id",
            {"project": project, "ids": fact_ids},
        )
        return [{"source": dict(row[1]), "fact_id": row[2]} for row in rows]

    def record_plan(self, project: str, expected: int, plan: dict, dependency_ids: list[str]):
        # Aggregate before creating the plan so the zero-dependency case still has one row.
        self._write(
            "MATCH (p:Project {id: $project, project_id: $project}) WHERE p.revision = $revision "
            "OPTIONAL MATCH (f:Fact {project_id: $project, status: 'active'}) WHERE f.id IN $ids "
            "WITH p, collect(f) AS dependencies WHERE size(dependencies) = size($ids) "
            "CREATE (plan:Plan) SET plan = $plan "
            "FOREACH (f IN dependencies | CREATE (plan)-[:DEPENDS_ON]->(f)) "
            "SET p.revision = $revision + 1 RETURN p.revision",
            {"project": project, "revision": expected, "plan": plan, "ids": dependency_ids},
        )

    def revise_plan(self, project, expected, previous_id, plan, dependency_ids):
        self._write(
            "MATCH (p:Project {id: $project, project_id: $project}), "
            "(old:Plan {id: $previous, project_id: $project}) "
            "WHERE p.revision = $revision AND old.status <> 'superseded' "
            "OPTIONAL MATCH (f:Fact {project_id: $project, status: 'active'}) WHERE f.id IN $ids "
            "WITH p, old, collect(f) AS dependencies WHERE size(dependencies) = size($ids) "
            "CREATE (plan:Plan) SET plan = $plan "
            "CREATE (plan)-[:REVISES]->(old) "
            "FOREACH (f IN dependencies | CREATE (plan)-[:DEPENDS_ON]->(f)) "
            "SET old.status = 'superseded', old.superseded_at = $plan.recorded_at, "
            "p.revision = $revision + 1 RETURN p.revision",
            {"project": project, "revision": expected, "previous": previous_id,
             "plan": plan, "ids": dependency_ids},
        )

    def create_handoff(self, project, expected, handoff, fact_ids):
        self._write(
            "MATCH (p:Project {id: $project, project_id: $project}), "
            "(plan:Plan {project_id: $project, id: $handoff.plan_id}) "
            "WHERE p.revision = $revision AND plan.status <> 'superseded' "
            "OPTIONAL MATCH (f:Fact {project_id: $project, status: 'active'}) WHERE f.id IN $ids "
            "WITH p, plan, collect(f) AS facts WHERE size(facts) = size($ids) "
            "MERGE (sender:Agent {project_id: $project, id: $handoff.from_agent}) "
            "CREATE (h:Handoff) SET h = $handoff "
            "CREATE (sender)-[:HANDED_OFF]->(h), (h)-[:CONCERNS]->(plan) "
            "FOREACH (f IN facts | CREATE (h)-[:CITES]->(f)) "
            "FOREACH (name IN CASE WHEN $handoff.to_agent IS NULL THEN [] ELSE [$handoff.to_agent] END | "
            "MERGE (receiver:Agent {project_id: $project, id: name}) CREATE (h)-[:ASSIGNED_TO]->(receiver)) "
            "SET p.revision = $revision + 1 RETURN p.revision",
            {"project": project, "revision": expected, "handoff": handoff, "ids": fact_ids},
        )

    def claim_handoff(self, project, expected, handoff_id, agent, claimed_at):
        # status = 'open' in the same write makes concurrent claims single-winner.
        self._write(
            "MATCH (p:Project {id: $project, project_id: $project}), "
            "(h:Handoff {project_id: $project, id: $id}) "
            "WHERE p.revision = $revision AND h.status = 'open' "
            "MERGE (a:Agent {project_id: $project, id: $agent}) CREATE (a)-[:CLAIMED]->(h) "
            "SET h.status = 'claimed', h.claimed_by = $agent, h.claimed_at = $at, "
            "p.revision = $revision + 1 RETURN p.revision",
            {"project": project, "revision": expected, "id": handoff_id, "agent": agent, "at": claimed_at},
        )

    def open_handoffs(self, project, scope):
        rows = self.query(
            "MATCH (h:Handoff {project_id: $project, scope: $scope, status: 'open'}) "
            "RETURN properties(h) ORDER BY h.recorded_at, h.id",
            {"project": project, "scope": scope},
        )
        return [dict(row[0]) for row in rows]

    def handoff_fact_ids(self, project, handoff_id):
        rows = self.query(
            "MATCH (h:Handoff {project_id: $project, id: $id})-[:CITES]->(f:Fact {project_id: $project}) "
            "RETURN f.id ORDER BY f.id", {"project": project, "id": handoff_id},
        )
        return [row[0] for row in rows]

    def current_plan(self, project, plan_id):
        """Follow REVISES backwards to the plan version that is not superseded."""
        rows = self.query(
            "MATCH path=(latest:Plan {project_id: $project})-[:REVISES*0..32]->"
            "(:Plan {project_id: $project, id: $plan}) WHERE latest.status <> 'superseded' "
            "AND all(n IN nodes(path) WHERE n.project_id = $project) "
            "RETURN latest.id, latest.status ORDER BY length(path) DESC LIMIT 1",
            {"project": project, "plan": plan_id},
        )
        return {"plan_id": rows[0][0], "status": rows[0][1]} if rows else None

    def current_fact(self, project, fact_id):
        """Follow SUPERSEDES backwards to the active replacement, if one exists."""
        rows = self.query(
            "MATCH path=(latest:Fact {project_id: $project, status: 'active'})-[:SUPERSEDES*0..32]->"
            "(:Fact {project_id: $project, id: $fact}) "
            "WHERE all(n IN nodes(path) WHERE n.project_id = $project) "
            "RETURN latest.id ORDER BY length(path) DESC LIMIT 1",
            {"project": project, "fact": fact_id},
        )
        return rows[0][0] if rows else None

    def record_event(self, project: str, expected: int, source: dict, event: dict,
                     new_fact: dict | None, target_id: str | None):
        params = {"project": project, "revision": expected, "source": source, "event": event}
        prefix = (
            "MATCH (p:Project {id: $project, project_id: $project}) WHERE p.revision = $revision "
        )
        # Resolve the old fact and dependent plans before any writes.
        if new_fact:
            prefix += (
                "MATCH (old:Fact {project_id: $project, id: $target, status: 'active'}) "
                "OPTIONAL MATCH (plan:Plan {project_id: $project})-[:DEPENDS_ON]->(old) "
                "WHERE plan.status <> 'superseded' "
                "WITH p, old, collect(DISTINCT plan) AS plans "
            )
            params.update({"target": target_id, "new_fact": new_fact})
        statement = prefix + (
            "MERGE (s:Source {id: $source.id, project_id: $project}) ON CREATE SET s = $source "
            "CREATE (e:UpdateEvent) SET e = $event CREATE (e)-[:BASED_ON]->(s) "
        )
        if new_fact:
            statement += (
                "CREATE (f:Fact) SET f = $new_fact "
                "SET old.status = 'superseded', old.superseded_at = $event.recorded_at "
                "CREATE (p)-[:HAS_FACT]->(f), (s)-[:SUPPORTS]->(f), "
                "(f)-[:SUPERSEDES]->(old), (e)-[:RETIRED]->(old), (e)-[:ACCEPTED]->(f) "
                "FOREACH (plan IN plans | SET plan.status = 'needs_review' "
                "CREATE (e)-[:FLAGGED]->(plan)) "
            )
        self._write(statement + "SET p.revision = $revision + 1 RETURN p.revision", params)

    def recall(self, project: str, scope: str, subjects: list[str]) -> dict:
        params = {"project": project, "scope": scope, "subjects": subjects}
        facts = self.query(
            "MATCH (f:Fact {project_id: $project, scope: $scope, status: 'active'}) "
            "WHERE size($subjects) = 0 OR f.subject IN $subjects RETURN properties(f) ORDER BY f.id",
            params,
        )
        plans = self.query(
            "MATCH (p:Plan {project_id: $project, scope: $scope, status: 'needs_review'}) "
            "RETURN properties(p) ORDER BY p.id", params,
        )
        pending = self.query(
            "MATCH (e:UpdateEvent {project_id: $project, scope: $scope, outcome: 'pending'}) "
            "RETURN e.result_json ORDER BY e.id", params,
        )
        import json

        active = [dict(row[0]) for row in facts]
        warnings = []
        for row in plans:
            plan = dict(row[0])
            plan.pop("review_fingerprint", None)
            plan.pop("review_result_json", None)
            paths = self.query(
                "MATCH (e:UpdateEvent {project_id: $project})-[:FLAGGED]->"
                "(p:Plan {project_id: $project, id: $plan}), "
                "(e)-[:RETIRED]->(f:Fact {project_id: $project})<-[:DEPENDS_ON]-(p) "
                "RETURN e.id, f.id ORDER BY e.id, f.id",
                {"project": project, "plan": plan["id"]},
            )
            warnings.append({"plan": plan, "explanation_paths": [
                {"event_id": item[0], "plan_id": plan["id"], "fact_id": item[1],
                 "relationship": "DEPENDS_ON"} for item in paths
            ]})
        return {"active_facts": active,
                "sources": self.sources(project, [fact["id"] for fact in active]),
                "affected_plans": warnings,
                "pending_conflicts": [json.loads(row[0]) for row in pending]}

    def history(self, project: str, fact_id: str) -> dict:
        # Both traversals are bounded and retain only nodes in the requested project.
        rows = self.query(
            "MATCH (start:Fact {project_id: $project, id: $fact}) "
            "MATCH path=(start)-[:SUPERSEDES*0..32]-(f:Fact) "
            "WHERE all(n IN nodes(path) WHERE n.project_id = $project) "
            "RETURN DISTINCT properties(f) ORDER BY f.recorded_at, f.id",
            {"project": project, "fact": fact_id},
        )
        facts = [dict(row[0]) for row in rows]
        ids = [fact["id"] for fact in facts]
        params = {"project": project, "ids": ids}
        links = self.query(
            "MATCH (a:Fact {project_id: $project})-[:SUPERSEDES]->(b:Fact {project_id: $project}) "
            "WHERE a.id IN $ids AND b.id IN $ids RETURN a.id, b.id ORDER BY a.id", params,
        )
        events = self.query(
            "MATCH (e:UpdateEvent {project_id: $project})-[:RETIRED|ACCEPTED]->"
            "(f:Fact {project_id: $project}) WHERE f.id IN $ids "
            "RETURN DISTINCT e.result_json ORDER BY e.result_json", params,
        )
        import json

        return {"facts": facts, "sources": self.sources(project, ids),
                "replacement_links": [{"new_fact_id": a, "old_fact_id": b} for a, b in links],
                "events": [json.loads(row[0]) for row in events]}

    def list_projects(self):
        rows = self.query("MATCH (p:Project) RETURN properties(p) ORDER BY p.name, p.id LIMIT 101", {})
        return {"projects": [dict(row[0]) for row in rows[:100]], "truncated": len(rows) > 100}

    def dashboard_snapshot(self, project, scope=None):
        """Bound every panel independently; preserve real graph edges and totals."""
        params = {"project": project, "scope": scope}
        truncated = {}
        counts = {}

        def panel(label, condition, name):
            clause = f"MATCH (n:{label} {{project_id: $project}}) WHERE "
            clause += "($scope IS NULL OR n.scope = $scope) AND " + condition
            counts[name] = self.query(clause + " RETURN count(n)", params)[0][0]
            rows = self.query(clause + " RETURN properties(n) ORDER BY n.recorded_at DESC, n.id LIMIT 201", params)
            truncated[name] = len(rows) > 200
            return [dict(row[0]) for row in rows[:200]]

        active = panel("Fact", "n.status = 'active'", "active")
        historical = panel("Fact", "n.status = 'superseded'", "superseded")
        affected = panel("Plan", "n.status = 'needs_review'", "affected")
        plans = panel("Plan", "true", "plans")
        # Keep affected plans visible even if they fall outside the recent-plan panel.
        plans = list({plan["id"]: plan for plan in plans + affected}.values())
        for plan in plans:
            plan.pop("review_fingerprint", None)
            plan.pop("review_result_json", None)
        pending = panel("UpdateEvent", "n.outcome IN ['pending', 'proposal']", "pending")
        recent = panel("UpdateEvent", "true", "updates")
        updates = list({event["id"]: event for event in recent + pending}.values())
        facts = active + historical
        edge_params = {"project": project, "facts": [n["id"] for n in facts],
                       "plans": [n["id"] for n in plans], "events": [n["id"] for n in updates]}
        # Edges touching displayed facts/plans/events may reach another scope in
        # this project. Expose that scope explicitly, never invent an endpoint.
        edges = self.query(
            "MATCH (a {project_id: $project})-[r]->(b {project_id: $project}) WHERE "
            "(type(r) = 'SUPPORTS' AND 'Fact' IN labels(b) AND b.id IN $facts) OR "
            "(type(r) = 'SUPERSEDES' AND 'Fact' IN labels(a) AND a.id IN $facts) OR "
            "(type(r) = 'DEPENDS_ON' AND 'Plan' IN labels(a) AND a.id IN $plans) OR "
            "(type(r) = 'REVISES' AND 'Plan' IN labels(a) AND (a.id IN $plans OR b.id IN $plans)) OR "
            "(type(r) IN ['BASED_ON', 'RETIRED', 'ACCEPTED', 'FLAGGED'] AND 'UpdateEvent' IN labels(a) AND a.id IN $events) "
            "RETURN type(r), properties(a), properties(b) ORDER BY type(r), a.id, b.id LIMIT 1001",
            edge_params,
        )
        truncated["edges"] = len(edges) > 1000
        paths = self.query(
            "MATCH (e:UpdateEvent {project_id: $project})-[:FLAGGED]->"
            "(p:Plan {project_id: $project}), "
            "(e)-[:RETIRED]->(f:Fact {project_id: $project})<-[:DEPENDS_ON]-(p) "
            "WHERE p.id IN $plans RETURN properties(e), properties(p), properties(f) "
            "ORDER BY e.id, p.id, f.id LIMIT 1001", edge_params,
        )
        truncated["explanation_paths"] = len(paths) > 1000
        scopes = self.query(
            "MATCH (n {project_id: $project}) WHERE n.scope IS NOT NULL "
            "RETURN DISTINCT n.scope ORDER BY n.scope LIMIT 201", {"project": project},
        )
        truncated["scopes"] = len(scopes) > 200
        # Event nodes in edges would expose replay internals and duplicate bodies.
        def endpoint(node):
            return {key: value for key, value in dict(node).items()
                    if key not in ("fingerprint", "result_json", "review_fingerprint", "review_result_json")}

        return {"facts": facts, "plans": plans, "updates": updates, "counts": counts,
                "scopes": [row[0] for row in scopes[:200]], "truncated": truncated,
                "edges": [{"relationship": kind, "from": endpoint(a), "to": endpoint(b)}
                          for kind, a, b in edges[:1000]],
                "explanation_paths": [{"event": endpoint(e), "plan": endpoint(p), "fact": endpoint(f)}
                                      for e, p, f in paths[:1000]]}
