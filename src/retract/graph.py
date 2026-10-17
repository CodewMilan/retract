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
        if label not in {"Project", "Source", "Fact", "Plan", "UpdateEvent"}:
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
            "RETURN p.id, f.id ORDER BY p.id",
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
