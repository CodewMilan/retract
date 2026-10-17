"""Pure decision policy; classification never grants permission by itself."""

from dataclasses import dataclass

from .models import UpdateInput


@dataclass(frozen=True)
class Decision:
    outcome: str
    reason: str


def decide(update: UpdateInput, active_fact: dict | None) -> Decision:
    if update.classification == "proposal":
        return Decision("proposal", "A proposal does not change accepted memory")
    if update.classification == "unrelated":
        return Decision("ignored", "Update is unrelated to the declared target")
    if update.classification == "ambiguous":
        return Decision("pending", "Ambiguous update requires developer review")
    if not update.confirmation:
        return Decision("pending", "Explicit developer confirmation is required")
    if not update.source.authoritative:
        return Decision("pending", "Source is not authoritative in the local developer workflow")
    if update.candidate is None or update.target_fact_id is None:
        return Decision("pending", "An explicit candidate and target fact are required")
    if active_fact is None:
        return Decision("pending", "No active fact matches the declared scoped key")
    candidate = update.candidate
    expected = (update.project_id, update.scope, candidate.subject, candidate.predicate)
    actual = tuple(active_fact.get(key) for key in ("project_id", "scope", "subject", "predicate"))
    if actual != expected or active_fact.get("status") != "active":
        return Decision("pending", "Target is not active in the declared project, scope, and key")
    if active_fact["id"] != update.target_fact_id:
        return Decision("pending", "Target changed; inspect current memory before confirming again")
    if active_fact["value"] == candidate.value:
        return Decision("no_change", "The accepted fact already has this value")
    return Decision("applied", "Confirmed authoritative replacement of the declared scoped fact")
