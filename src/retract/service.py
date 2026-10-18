"""Application boundary shared by future MCP and dashboard adapters."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from threading import RLock
from uuid import uuid4

from .graph import GraphStore
from .activity import ActivityJournal
from .models import (
    ClaimInput, ConflictError, HandoffInput, NaturalUpdateInput, NotFoundError, PlanInput, PlanRevisionInput,
    RememberInput, UpdateInput, identifier, text,
)
from .policy import decide


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def generated_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class MemoryService:
    def __init__(self, store: GraphStore, interpreter=None):
        self.store = store
        self.lock = RLock()
        self.interpreter = interpreter
        self.activity = ActivityJournal()

    def list_projects(self):
        with self.lock:
            return self.store.list_projects()

    def dashboard(self, project_id: str, scope: str | None = None):
        if scope is not None:
            identifier(scope, "scope")
        with self.lock:
            project = self.project(project_id)
            snapshot = self.store.dashboard_snapshot(project_id, scope)
            # Internal replay fingerprints are not dashboard data.
            for event in snapshot["updates"]:
                event["result"] = json.loads(event.pop("result_json"))
                event.pop("fingerprint", None)
            return {**snapshot, "project": project, "observed_at": timestamp(),
                    "activity": self.activity.read(project_id, scope),
                    "activity_retention": "service_process"}

    def project(self, project_id: str, expected: int | None = None) -> dict:
        identifier(project_id, "project_id")
        project = self.store.get("Project", project_id, project_id)
        if project is None:
            raise NotFoundError("Project does not exist; create it explicitly first")
        if expected is not None and expected != project["revision"]:
            raise ConflictError("Stale project revision; retrieve context before retrying")
        return project

    def create_project(self, project_id: str, name: str) -> dict:
        identifier(project_id, "project_id")
        text(name, "name", 300)
        with self.lock:
            existing = self.store.get("Project", project_id, project_id)
            if existing and existing["name"] != name:
                raise ConflictError("Project ID already has a different name")
            return existing or self.store.create_project(project_id, name)

    def _source(self, project: str, source) -> dict:
        incoming = asdict(source)
        existing = self.store.get("Source", project, source.id)
        if existing:
            if any(existing.get(key) != value for key, value in incoming.items()):
                raise ConflictError("Source IDs are immutable; use a new ID for changed evidence")
            return existing
        return {**incoming, "project_id": project, "recorded_at": timestamp()}

    def remember(self, request: RememberInput) -> dict:
        with self.lock:
            project = self.project(request.project_id, request.expected_revision)
            if not request.source.authoritative:
                raise ConflictError("Accepted memory requires an authoritative source")
            source = self._source(request.project_id, request.source)
            current = self.store.active(request.project_id, request.scope, request.subject, request.predicate)
            if current:
                if current["value"] != request.value:
                    raise ConflictError("Key already has an active value; use process_update")
                links = self.store.sources(request.project_id, [current["id"]])
                if not any(link["source"]["id"] == source["id"] for link in links):
                    self.store.attach_source(request.project_id, project["revision"], source, current["id"])
                    project = {**project, "revision": project["revision"] + 1}
                return {"fact_id": current["id"], "status": "active", "outcome": "duplicate",
                        "project_revision": project["revision"]}
            fact_id = request.fact_id or generated_id("fact")
            if self.store.get("Fact", request.project_id, fact_id):
                raise ConflictError("Fact ID already exists")
            fact = {"id": fact_id, "project_id": request.project_id, "scope": request.scope,
                    "subject": request.subject, "predicate": request.predicate, "value": request.value,
                    "status": "active", "recorded_at": timestamp()}
            self.store.remember(request.project_id, project["revision"], source, fact)
            return {"fact_id": fact_id, "status": "active", "outcome": "created",
                    "project_revision": project["revision"] + 1}

    def record_plan(self, request: PlanInput) -> dict:
        with self.lock:
            project = self.project(request.project_id, request.expected_revision)
            plan_id = request.plan_id or generated_id("plan")
            plan = {"id": plan_id, "project_id": request.project_id, "scope": request.scope,
                    "text": request.text, "status": "current"}
            existing = self.store.get("Plan", request.project_id, plan_id)
            if existing:
                # Never let reseeding reset a flagged plan to current.
                if any(existing.get(key) != plan[key] for key in ("scope", "text")):
                    raise ConflictError("Plan ID already exists with different content")
                if sorted(self.store.plan_dependencies(request.project_id, plan_id)) != sorted(request.dependency_fact_ids):
                    raise ConflictError("Plan ID already exists with different dependencies")
                return {"plan_id": plan_id, "status": existing["status"], "outcome": "duplicate",
                        "project_revision": project["revision"]}
            for fact_id in request.dependency_fact_ids:
                fact = self.store.get("Fact", request.project_id, fact_id)
                if not fact or fact["status"] != "active":
                    raise ConflictError("Plan dependencies must be active facts in this project")
            self.store.record_plan(request.project_id, project["revision"], plan, request.dependency_fact_ids)
            return {"plan_id": plan_id, "status": "current", "outcome": "created",
                    "project_revision": project["revision"] + 1}

    def revise_plan(self, request: PlanRevisionInput) -> dict:
        fingerprint = hashlib.sha256(json.dumps(asdict(request), sort_keys=True).encode()).hexdigest()
        with self.lock:
            self.project(request.project_id)
            existing = self.store.get("Plan", request.project_id, request.replacement_plan_id)
            if existing:
                if existing.get("review_fingerprint") != fingerprint:
                    raise ConflictError("Replacement plan ID already exists with different content")
                return json.loads(existing["review_result_json"])
            project = self.project(request.project_id, request.expected_revision)
            previous = self.store.get("Plan", request.project_id, request.plan_id)
            if not previous:
                raise NotFoundError("Plan does not exist in this project")
            if previous["status"] == "superseded":
                raise ConflictError("This plan was already revised; review its replacement")
            for fact_id in request.dependency_fact_ids:
                fact = self.store.get("Fact", request.project_id, fact_id)
                if not fact or fact["status"] != "active":
                    raise ConflictError("Plan dependencies must be active facts in this project")
            result = {"plan_id": request.replacement_plan_id, "previous_plan_id": request.plan_id,
                      "status": "current", "outcome": "revised", "project_revision": project["revision"] + 1}
            plan = {"id": request.replacement_plan_id, "project_id": request.project_id,
                    "scope": previous["scope"], "text": request.text, "status": "current",
                    "recorded_at": timestamp(), "review_reason": request.reason,
                    "supersedes_plan_id": request.plan_id, "review_fingerprint": fingerprint,
                    "review_result_json": json.dumps(result, sort_keys=True)}
            self.store.revise_plan(request.project_id, project["revision"], request.plan_id,
                                   plan, request.dependency_fact_ids)
            return result

    def process_natural_update(self, request: NaturalUpdateInput) -> dict:
        from .inference import GroqInterpreter

        fingerprint = hashlib.sha256(json.dumps(
            {"kind": "natural_update_v1", "request": asdict(request)}, sort_keys=True,
        ).encode()).hexdigest()
        with self.lock:
            self.project(request.project_id)
            existing = self.store.get("UpdateEvent", request.project_id, request.event_id)
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise ConflictError("Event ID was already used for a different request")
                return json.loads(existing["result_json"])
            project = self.project(request.project_id, request.expected_revision)
            self._source(request.project_id, request.source)
            current = self.store.active(request.project_id, request.scope, request.subject, request.predicate)
        # Network waits must not block recall or unrelated writes. A revision guard
        # below refuses to apply extraction to a project changed during inference.
        interpreter = self.interpreter if self.interpreter is not None else GroqInterpreter.from_env()
        interpreted = interpreter.extract(request, current)
        structured = interpreted.extraction.to_update(request, current, project["revision"])
        return self.process_update(structured, _fingerprint=fingerprint, _interpretation=interpreted.audit())

    def process_update(self, request: UpdateInput, *, _fingerprint: str | None = None,
                       _interpretation: dict | None = None) -> dict:
        fingerprint = _fingerprint or hashlib.sha256(json.dumps(asdict(request), sort_keys=True).encode()).hexdigest()
        with self.lock:
            # Replay lookup precedes revision checking: exact retries survive revision changes.
            self.project(request.project_id)
            existing = self.store.get("UpdateEvent", request.project_id, request.event_id)
            if existing:
                if existing["fingerprint"] != fingerprint:
                    raise ConflictError("Event ID was already used for a different request")
                return json.loads(existing["result_json"])
            project = self.project(request.project_id, request.expected_revision)
            source = self._source(request.project_id, request.source)
            current = None
            if request.candidate:
                current = self.store.active(request.project_id, request.scope,
                                            request.candidate.subject, request.candidate.predicate)
            decision = decide(request, current)
            new_fact = None
            paths = []
            if decision.outcome == "applied":
                replacement_id = request.replacement_fact_id or generated_id("fact")
                if self.store.get("Fact", request.project_id, replacement_id):
                    raise ConflictError("Replacement fact ID already exists")
                new_fact = {"id": replacement_id, "project_id": request.project_id,
                            "scope": request.scope, "subject": request.candidate.subject,
                            "predicate": request.candidate.predicate, "value": request.candidate.value,
                            "status": "active", "recorded_at": timestamp()}
                paths = self.store.dependent_paths(request.project_id, current["id"])
            result = {"event_id": request.event_id, "classification": request.classification,
                      "outcome": decision.outcome, "reason": decision.reason, "source_id": source["id"],
                      "retired_fact_ids": [current["id"]] if new_fact else [],
                      "accepted_fact_ids": [new_fact["id"]] if new_fact else [],
                      "flagged_plan_ids": sorted({path["plan_id"] for path in paths}),
                      "explanation_paths": paths, "candidate": asdict(request.candidate) if request.candidate else None,
                      "expected_revision": project["revision"], "resulting_revision": project["revision"] + 1}
            if _interpretation is not None:
                result["interpretation"] = _interpretation
            event = {"id": request.event_id, "project_id": request.project_id, "scope": request.scope,
                     "text": request.text, "classification": request.classification,
                     "outcome": decision.outcome, "reason": decision.reason,
                     "recorded_at": timestamp(), "fingerprint": fingerprint,
                     "expected_revision": project["revision"], "resulting_revision": project["revision"] + 1,
                     "result_json": json.dumps(result, sort_keys=True)}
            self.store.record_event(request.project_id, project["revision"], source, event,
                                    new_fact, current["id"] if new_fact else None)
            return result

    def recall(self, project_id: str, scope: str, subjects: list[str] | None = None) -> dict:
        identifier(scope, "scope")
        subjects = [] if subjects is None else subjects
        if not isinstance(subjects, list) or len(subjects) > 32:
            from .models import ValidationError
            raise ValidationError("subjects must be a list of at most 32 identifiers")
        for subject in subjects:
            identifier(subject, "subject")
        with self.lock:
            project = self.project(project_id)
            recalled = self.store.recall(project_id, scope, subjects)
            for warning in recalled["affected_plans"]:
                warning["dependencies"] = self._dependency_status(
                    project_id, self.store.plan_dependencies(project_id, warning["plan"]["id"]))
                warning["handoffs"] = [
                    {key: item.get(key) for key in ("id", "from_agent", "to_agent", "status", "claimed_by")}
                    for item in self.store.plan_handoffs(project_id, warning["plan"]["id"])]
            handoffs = [self._handoff_context(project_id, item)
                        for item in self.store.open_handoffs(project_id, scope)]
            return {**recalled, "open_handoffs": handoffs, "project_revision": project["revision"]}

    def _dependency_status(self, project_id: str, fact_ids: list[str]) -> list[dict]:
        result = []
        for fact_id in fact_ids:
            current = self.store.current_fact(project_id, fact_id)
            result.append({"fact_id": fact_id, "current_fact_id": current, "changed": current != fact_id})
        return result

    def _handoff_context(self, project_id: str, handoff: dict) -> dict:
        """Compare what the sender relied on with what the graph says is current now."""
        handoff = {key: value for key, value in handoff.items() if key != "fingerprint"}
        plan = self.store.current_plan(project_id, handoff["plan_id"])
        facts = self._dependency_status(project_id, self.store.handoff_fact_ids(project_id, handoff["id"]))
        warnings = []
        if plan is None:
            warnings.append(f"Plan {handoff['plan_id']} has no current version")
        elif plan["plan_id"] != handoff["plan_id"]:
            warnings.append(f"Plan {handoff['plan_id']} was revised; current version is {plan['plan_id']}")
        elif plan["status"] == "needs_review":
            warnings.append(f"Plan {plan['plan_id']} still needs review")
        for item in facts:
            if item["changed"]:
                replacement = item["current_fact_id"] or "no active replacement"
                warnings.append(f"Fact {item['fact_id']} was superseded; current: {replacement}")
        return {"handoff": handoff, "current_plan": plan, "cited_facts": facts,
                "stale": bool(warnings), "warnings": warnings}

    def create_handoff(self, request: HandoffInput) -> dict:
        fingerprint = hashlib.sha256(json.dumps(asdict(request), sort_keys=True).encode()).hexdigest()
        with self.lock:
            self.project(request.project_id)
            existing = self.store.get("Handoff", request.project_id, request.handoff_id)
            if existing:
                if existing.get("fingerprint") != fingerprint:
                    raise ConflictError("Handoff ID already exists with different content")
                return {"handoff_id": existing["id"], "status": existing["status"], "outcome": "duplicate",
                        "project_revision": self.project(request.project_id)["revision"]}
            project = self.project(request.project_id, request.expected_revision)
            plan = self.store.get("Plan", request.project_id, request.plan_id)
            if not plan or plan["status"] == "superseded":
                raise ConflictError("Hand off the current version of an existing plan")
            if plan["scope"] != request.scope:
                raise ConflictError("Handoff scope must match the plan scope")
            for fact_id in request.fact_ids:
                fact = self.store.get("Fact", request.project_id, fact_id)
                if not fact or fact["status"] != "active":
                    raise ConflictError("Handoffs may cite only active facts in this project")
            handoff = {"id": request.handoff_id, "project_id": request.project_id, "scope": request.scope,
                       "from_agent": request.from_agent, "plan_id": request.plan_id, "note": request.note,
                       "status": "open", "recorded_at": timestamp(), "fingerprint": fingerprint}
            if request.to_agent is not None:
                handoff["to_agent"] = request.to_agent
            self.store.create_handoff(request.project_id, project["revision"], handoff, request.fact_ids)
            return {"handoff_id": request.handoff_id, "status": "open", "outcome": "created",
                    "project_revision": project["revision"] + 1}

    def claim_handoff(self, request: ClaimInput) -> dict:
        with self.lock:
            self.project(request.project_id)
            handoff = self.store.get("Handoff", request.project_id, request.handoff_id)
            if handoff is None:
                raise NotFoundError("Handoff not found in this project")
            if handoff["status"] == "claimed":
                if handoff.get("claimed_by") != request.agent:
                    raise ConflictError(f"Handoff already claimed by {handoff.get('claimed_by')}")
                return {**self._handoff_context(request.project_id, handoff), "outcome": "duplicate",
                        "project_revision": self.project(request.project_id)["revision"]}
            if handoff.get("to_agent") not in (None, request.agent):
                raise ConflictError(f"Handoff is assigned to {handoff['to_agent']}")
            if handoff["from_agent"] == request.agent:
                raise ConflictError("An agent cannot claim its own handoff")
            project = self.project(request.project_id, request.expected_revision)
            self.store.claim_handoff(request.project_id, project["revision"], request.handoff_id,
                                     request.agent, timestamp())
            claimed = self.store.get("Handoff", request.project_id, request.handoff_id)
            return {**self._handoff_context(request.project_id, claimed), "outcome": "claimed",
                    "project_revision": project["revision"] + 1}

    def history(self, project_id: str, *, fact_id: str | None = None, event_id: str | None = None) -> dict:
        from .models import ValidationError

        if (fact_id is None) == (event_id is None):
            raise ValidationError("Supply exactly one of fact_id or event_id")
        with self.lock:
            project = self.project(project_id)
            if event_id is not None:
                identifier(event_id, "event_id")
                event = self.store.get("UpdateEvent", project_id, event_id)
                if event is None:
                    raise NotFoundError("Event not found in this project")
                result = json.loads(event["result_json"])
                source = self.store.get("Source", project_id, result["source_id"])
                return {"event": result, "source": source, "project_revision": project["revision"]}
            identifier(fact_id, "fact_id")
            if self.store.get("Fact", project_id, fact_id) is None:
                raise NotFoundError("Fact not found in this project")
            return {**self.store.history(project_id, fact_id), "project_revision": project["revision"]}
