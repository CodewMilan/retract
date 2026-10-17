"""Application boundary shared by future MCP and dashboard adapters."""

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from threading import RLock
from uuid import uuid4

from .graph import GraphStore
from .models import (
    ConflictError, NotFoundError, PlanInput, RememberInput, UpdateInput,
    identifier, text,
)
from .policy import decide


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def generated_id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


class MemoryService:
    def __init__(self, store: GraphStore):
        self.store = store
        self.lock = RLock()

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

    def process_update(self, request: UpdateInput) -> dict:
        fingerprint = hashlib.sha256(json.dumps(asdict(request), sort_keys=True).encode()).hexdigest()
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
            return {**self.store.recall(project_id, scope, subjects), "project_revision": project["revision"]}

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
