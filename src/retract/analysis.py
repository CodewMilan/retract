"""Read-only graph investigation over FalkorDB: multi-hop paths and graph algorithms.

Every query runs through GRAPH.RO_QUERY, is filtered to one project and bounded.
FalkorDB's algorithm procedures run over the whole graph; results are filtered to
the project afterwards, so scores are relative ranks, not per-project absolutes.
"""

import json

from .models import NotFoundError, ValidationError, identifier

TOOLS = ("overview", "findings", "centrality", "blast_radius", "trace", "components")
HIDDEN = {"fingerprint", "result_json", "review_fingerprint", "review_result_json", "project_id"}
SHOWN = ("scope", "subject", "predicate", "value", "status", "outcome", "classification", "title",
         "authority", "kind", "from_agent", "to_agent", "claimed_by", "text", "reason")
TRUSTED = ["developer", "approved_document"]
ALGORITHMS = ("pagerank", "betweenness")
# HAS_FACT links everything to the Project hub; traversing it would connect unrelated facts.
LINKS = "SUPPORTS|DEPENDS_ON|SUPERSEDES|REVISES|RETIRED|ACCEPTED|FLAGGED|BASED_ON|CONCERNS|CITES|HANDED_OFF|ASSIGNED_TO|CLAIMED"


def _clip(value, limit=240):
    return value if not isinstance(value, str) or len(value) <= limit else value[:limit] + "…"


def node_view(label, props):
    props = dict(props)
    view = {"label": label, "id": props.get("id")}
    view.update({key: _clip(props[key]) for key in SHOWN if key in props and key not in HIDDEN})
    return view


def _edges(rows):
    return [{"type": kind, "from": start, "to": end} for kind, start, end in rows]


class GraphAnalysis:
    def __init__(self, store):
        if not hasattr(store, "graph"):
            raise ValidationError("Graph analysis requires the FalkorDB store")
        self.store = store

    def q(self, statement, params):
        return self.store.query(statement, params)

    def run(self, project, tool, args):
        if tool not in TOOLS:
            raise ValidationError(f"tool must be one of {', '.join(TOOLS)}")
        allowed = {"overview": set(), "findings": {"scope"}, "centrality": {"algorithm", "limit"},
                   "blast_radius": {"node_id", "depth"}, "trace": {"from_id", "to_id"},
                   "components": set()}[tool]
        if set(args) - allowed:
            raise ValidationError(f"{tool} accepts only: {', '.join(sorted(allowed)) or 'no arguments'}")
        return {"tool": tool, **getattr(self, tool)(project, **args)}

    def node(self, project, node_id):
        identifier(node_id, "node_id")
        rows = self.q("MATCH (n {project_id: $project, id: $id}) WHERE NOT n:Project "
                      "RETURN labels(n)[0], properties(n) LIMIT 3", {"project": project, "id": node_id})
        if not rows:
            raise NotFoundError(f"No node {node_id} in this project")
        if len(rows) > 1:
            raise ValidationError(f"Node ID {node_id} is ambiguous across labels")
        return rows[0]

    def overview(self, project):
        rows = self.q("MATCH (n {project_id: $project}) WHERE NOT n:Project "
                      "RETURN labels(n)[0], coalesce(n.status, n.outcome, ''), count(n)", {"project": project})
        counts = {}
        for label, status, total in rows:
            counts.setdefault(label, {})[status or "all"] = total
        edges = self.q("MATCH (a {project_id: $project})-[r]->(b {project_id: $project}) "
                       "RETURN type(r), count(r)", {"project": project})
        scopes = self.q("MATCH (n {project_id: $project}) WHERE n.scope IS NOT NULL "
                        "RETURN DISTINCT n.scope ORDER BY n.scope LIMIT 50", {"project": project})
        return {"nodes": counts, "relationships": dict(edges), "scopes": [row[0] for row in scopes]}

    def findings(self, project, scope=None):
        if scope is not None:
            identifier(scope, "scope")
        params = {"project": project, "scope": scope, "trusted": TRUSTED}
        found = []

        # 1. Live plans that still depend on a retired fact, with the current replacement.
        stale = {}
        for plan_id, plan_scope, status, old_id, current_id in self.q(
                "MATCH (p:Plan {project_id: $project})-[:DEPENDS_ON]->(f:Fact {project_id: $project, status: 'superseded'}) "
                "WHERE p.status <> 'superseded' AND ($scope IS NULL OR p.scope = $scope) "
                "OPTIONAL MATCH (cur:Fact {project_id: $project, status: 'active'})-[:SUPERSEDES*1..32]->(f) "
                "RETURN p.id, p.scope, p.status, f.id, cur.id ORDER BY p.id, f.id LIMIT 200", params):
            entry = stale.setdefault(plan_id, {"plan_id": plan_id, "scope": plan_scope, "status": status, "retired": []})
            entry["retired"].append({"fact_id": old_id, "current_fact_id": current_id})
        for entry in stale.values():
            active = [row[0] for row in self.q(
                "MATCH (:Plan {project_id: $project, id: $plan})-[:DEPENDS_ON]->(f:Fact {project_id: $project, status: 'active'}) "
                "RETURN f.id ORDER BY f.id", {**params, "plan": entry["plan_id"]})]
            current = sorted(set(active) | {r["current_fact_id"] for r in entry["retired"] if r["current_fact_id"]})
            found.append({"id": f"stale_plan:{entry['plan_id']}", "kind": "stale_plan", "severity": "high",
                          "plan_id": entry["plan_id"], "scope": entry["scope"], "current_fact_ids": current,
                          "evidence": entry["retired"],
                          "summary": f"Plan {entry['plan_id']} ({entry['status']}) depends on retired "
                                     + ", ".join(f"{r['fact_id']}→{r['current_fact_id'] or 'no replacement'}"
                                                 for r in entry["retired"])})

        # 2. Live plans relying on an active fact with no trusted supporting source.
        for plan_id, plan_scope, fact_id, authorities in self.q(
                "MATCH (p:Plan {project_id: $project})-[:DEPENDS_ON]->(f:Fact {project_id: $project, status: 'active'}) "
                "WHERE p.status <> 'superseded' AND ($scope IS NULL OR p.scope = $scope) "
                "OPTIONAL MATCH (s:Source {project_id: $project})-[:SUPPORTS]->(f) "
                "WITH p, f, collect(s.authority) AS authorities "
                "WHERE none(a IN authorities WHERE a IN $trusted) "
                "RETURN p.id, p.scope, f.id, authorities ORDER BY p.id, f.id LIMIT 200", params):
            found.append({"id": f"weak_evidence:{plan_id}:{fact_id}", "kind": "weak_evidence", "severity": "medium",
                          "plan_id": plan_id, "scope": plan_scope, "fact_id": fact_id,
                          "evidence": {"source_authorities": authorities},
                          "summary": f"Plan {plan_id} relies on {fact_id}, which has no developer or approved source"})

        # 3. Multi-hop drift: a correction retired value V for one scope while another
        #    scope still holds V for the same predicate. A lead, not a contradiction.
        for event_id, new_id, new_scope, new_value, old_id, predicate, old_value, other_id, other_scope, other_subject, plans in self.q(
                "MATCH (e:UpdateEvent {project_id: $project})-[:ACCEPTED]->(new:Fact {project_id: $project})"
                "-[:SUPERSEDES]->(old:Fact {project_id: $project}), "
                "(other:Fact {project_id: $project, status: 'active'}) "
                "WHERE other.scope <> old.scope AND other.predicate = old.predicate AND other.value = old.value "
                "AND ($scope IS NULL OR other.scope = $scope OR old.scope = $scope) "
                "OPTIONAL MATCH (p:Plan {project_id: $project})-[:DEPENDS_ON]->(other) WHERE p.status <> 'superseded' "
                "RETURN e.id, new.id, new.scope, new.value, old.id, old.predicate, old.value, other.id, other.scope, "
                "other.subject, collect(DISTINCT p.id) ORDER BY e.id, other.id LIMIT 100", params):
            found.append({"id": f"cross_scope_drift:{other_id}:{event_id}", "kind": "cross_scope_drift",
                          "severity": "medium" if plans else "low", "fact_id": other_id, "scope": other_scope,
                          "dependent_plan_ids": plans,
                          "evidence": {"path": [{"type": "ACCEPTED", "from": event_id, "to": new_id},
                                                {"type": "SUPERSEDES", "from": new_id, "to": old_id}],
                                       "shared": {"predicate": predicate, "retired_value": old_value}},
                          "summary": f"{event_id} replaced {predicate} '{old_value}' with '{new_value}' in {new_scope} "
                                     f"({old_id}→{new_id}); {other_id} ({other_subject}) in {other_scope} still says "
                                     f"'{old_value}'. Confirm whether the correction also applies there."})

        # 4. Open handoffs whose plan or cited facts changed after they were written.
        for handoff_id, plan_id, plan_status, to_agent, retired in self.q(
                "MATCH (h:Handoff {project_id: $project, status: 'open'})-[:CONCERNS]->(pl:Plan {project_id: $project}) "
                "WHERE $scope IS NULL OR h.scope = $scope "
                "OPTIONAL MATCH (h)-[:CITES]->(f:Fact {project_id: $project, status: 'superseded'}) "
                "WITH h, pl, collect(f.id) AS retired WHERE pl.status = 'superseded' OR size(retired) > 0 "
                "RETURN h.id, pl.id, pl.status, h.to_agent, retired ORDER BY h.id LIMIT 100", params):
            found.append({"id": f"stale_handoff:{handoff_id}", "kind": "stale_handoff", "severity": "medium",
                          "handoff_id": handoff_id, "plan_id": plan_id, "evidence": {"plan_status": plan_status,
                                                                                      "retired_cited_facts": retired},
                          "summary": f"Open handoff {handoff_id} for {to_agent or 'any agent'} concerns {plan_id} "
                                     f"({plan_status}) and cites retired {retired or 'nothing'}"})

        # 5. Unresolved updates (pending or proposal) that would touch a fact live plans use.
        for event_id, event_scope, outcome, result_json in self.q(
                "MATCH (e:UpdateEvent {project_id: $project}) WHERE e.outcome IN ['pending', 'proposal'] "
                "AND ($scope IS NULL OR e.scope = $scope) RETURN e.id, e.scope, e.outcome, e.result_json "
                "ORDER BY e.id LIMIT 100", params):
            candidate = (json.loads(result_json or "{}").get("candidate") or {})
            if not candidate.get("subject"):
                continue
            rows = self.q(
                "MATCH (f:Fact {project_id: $project, scope: $scope, subject: $subject, predicate: $predicate, status: 'active'}) "
                "OPTIONAL MATCH (p:Plan {project_id: $project})-[:DEPENDS_ON]->(f) WHERE p.status <> 'superseded' "
                "RETURN f.id, f.value, collect(DISTINCT p.id)",
                {"project": project, "scope": event_scope, "subject": candidate["subject"],
                 "predicate": candidate["predicate"]})
            for fact_id, value, plans in rows:
                found.append({"id": f"unresolved_update:{event_id}", "kind": "unresolved_update",
                              "severity": "medium" if plans else "low", "fact_id": fact_id, "scope": event_scope,
                              "dependent_plan_ids": plans,
                              "summary": f"{outcome} {event_id} suggests '{_clip(candidate.get('value'), 120)}' for "
                                         f"{candidate['subject']} {candidate['predicate']} (now '{value}', {fact_id}); "
                                         f"not applied. Plans at risk: {plans or 'none'}"})
        order = {"high": 0, "medium": 1, "low": 2}
        found.sort(key=lambda item: (order[item["severity"]], item["id"]))
        return {"scope": scope, "findings": found}

    def centrality(self, project, algorithm="pagerank", limit=10):
        if algorithm not in ALGORITHMS:
            raise ValidationError(f"algorithm must be one of {', '.join(ALGORITHMS)}")
        if type(limit) is not int or not 1 <= limit <= 50:
            raise ValidationError("limit must be an integer from 1 to 50")
        call = ("CALL algo.pageRank(NULL, 'DEPENDS_ON')" if algorithm == "pagerank" else
                "CALL algo.betweenness({nodeLabels: ['Fact', 'Plan', 'Handoff'], "
                "relationshipTypes: ['DEPENDS_ON', 'SUPERSEDES', 'REVISES', 'CONCERNS', 'CITES']})")
        rows = self.q(
            call + " YIELD node, score WITH node, score WHERE node.project_id = $project AND node:Fact "
            "OPTIONAL MATCH (p:Plan {project_id: $project})-[:DEPENDS_ON]->(node) WHERE p.status <> 'superseded' "
            "RETURN properties(node), score, collect(DISTINCT p.id) ORDER BY score DESC, node.id LIMIT $limit",
            {"project": project, "limit": limit})
        return {"algorithm": algorithm, "ranked": [
            {**node_view("Fact", props), "score": round(score, 4), "dependent_plan_ids": plans}
            for props, score, plans in rows]}

    def blast_radius(self, project, node_id, depth=3):
        if type(depth) is not int or not 1 <= depth <= 4:
            raise ValidationError("depth must be an integer from 1 to 4")
        label, props = self.node(project, node_id)
        rows = self.q(
            f"MATCH path=(s {{project_id: $project, id: $id}})-[:{LINKS}*1..{depth}]-(n) "
            "WHERE NOT s:Project AND NOT n:Project AND n <> s AND all(x IN nodes(path) WHERE x.project_id = $project) "
            "WITH n, path ORDER BY length(path) WITH n, collect(path)[0] AS path "
            "RETURN labels(n)[0], properties(n), length(path) AS hops, "
            "[r IN relationships(path) | [type(r), startNode(r).id, endNode(r).id]] "
            "ORDER BY hops, labels(n)[0], n.id LIMIT 201", {"project": project, "id": node_id})
        reached = [{**node_view(kind, item), "hops": hops, "path": _edges(path)}
                   for kind, item, hops, path in rows[:200]]
        by_label = {}
        for item in reached:
            by_label.setdefault(item["label"], []).append(item["id"])
        return {"start": node_view(label, props), "depth": depth, "reached_by_label": by_label,
                "reached": reached, "truncated": len(rows) > 200}

    def trace(self, project, from_id, to_id):
        self.node(project, from_id)
        self.node(project, to_id)
        rows = self.q(
            "MATCH (s {project_id: $project, id: $from}), (t {project_id: $project, id: $to}) "
            "WHERE NOT s:Project AND NOT t:Project "
            f"WITH shortestPath((s)-[:{LINKS}*..8]-(t)) AS path WHERE path IS NOT NULL "
            "RETURN [n IN nodes(path) | [labels(n)[0], properties(n)]], "
            "[r IN relationships(path) | [type(r), startNode(r).id, endNode(r).id]]",
            {"project": project, "from": from_id, "to": to_id})
        if not rows:
            return {"from": from_id, "to": to_id, "connected": False, "nodes": [], "edges": []}
        nodes, edges = rows[0]
        return {"from": from_id, "to": to_id, "connected": True, "hops": len(edges),
                "nodes": [node_view(kind, props) for kind, props in nodes], "edges": _edges(edges)}

    def components(self, project):
        rows = self.q(
            "CALL algo.WCC({nodeLabels: ['Fact', 'Plan', 'Source', 'UpdateEvent', 'Handoff']}) "
            "YIELD node, componentId WITH node, componentId WHERE node.project_id = $project "
            "RETURN componentId, collect([labels(node)[0], node.id]) ORDER BY componentId LIMIT 200",
            {"project": project})
        groups = []
        for _, members in rows:
            labels = {}
            for kind, node_id in members:
                labels.setdefault(kind, []).append(node_id)
            groups.append({"size": len(members), "by_label": {k: sorted(v)[:50] for k, v in labels.items()}})
        groups.sort(key=lambda g: -g["size"])
        isolated = sorted(i for g in groups if "Plan" not in g["by_label"] for i in g["by_label"].get("Fact", []))
        return {"components": groups[:50], "facts_without_any_plan_in_component": isolated[:100]}
