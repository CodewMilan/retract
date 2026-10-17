"""Validated structured inputs. Source text is never parsed as an instruction."""

from dataclasses import asdict, dataclass, fields
from typing import Any, TypeVar
import re


class ValidationError(ValueError):
    pass


class ConflictError(ValueError):
    pass


class NotFoundError(ValueError):
    pass


IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,159}\Z")


def identifier(value: Any, name: str = "id") -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValidationError(f"{name} must be a 1–160 character identifier")
    return value


def text(value: Any, name: str, limit: int = 2000) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValidationError(f"{name} must contain 1–{limit} characters")
    return value


def revision(value: Any) -> None:
    if value is not None and (type(value) is not int or not 0 <= value < 2**63 - 1):
        raise ValidationError("expected_revision must be a nonnegative integer")


T = TypeVar("T")


def parse(cls: type[T], payload: Any) -> T:
    if not isinstance(payload, dict):
        raise ValidationError("Request must be a JSON object")
    unknown = set(payload) - {field.name for field in fields(cls)}
    if unknown:
        raise ValidationError(f"Unknown fields: {', '.join(sorted(unknown))}")
    values = dict(payload)
    if "source" in values:
        values["source"] = parse(SourceInput, values["source"])
    if "candidate" in values and values["candidate"] is not None:
        values["candidate"] = parse(Candidate, values["candidate"])
    try:
        return cls(**values)
    except TypeError as exc:
        raise ValidationError(f"Invalid {cls.__name__} fields") from exc


@dataclass(frozen=True)
class SourceInput:
    id: str
    kind: str
    title: str
    content: str
    authority: str = "untrusted"

    def __post_init__(self):
        identifier(self.id, "source.id")
        if self.kind not in ("developer", "document"):
            raise ValidationError("source.kind must be developer or document")
        text(self.title, "source.title", 300)
        text(self.content, "source.content", 16000)
        if self.authority not in ("developer", "approved_document", "untrusted"):
            raise ValidationError("Unknown source authority")
        if self.authority == "developer" and self.kind != "developer":
            raise ValidationError("Developer authority requires a developer source")
        if self.authority == "approved_document" and self.kind != "document":
            raise ValidationError("Approved document authority requires a document source")

    @property
    def authoritative(self) -> bool:
        return self.authority in ("developer", "approved_document")


@dataclass(frozen=True)
class Candidate:
    subject: str
    predicate: str
    value: str
    excerpt: str

    def __post_init__(self):
        identifier(self.subject, "subject")
        identifier(self.predicate, "predicate")
        text(self.value, "value")
        text(self.excerpt, "excerpt", 4000)


@dataclass(frozen=True)
class RememberInput:
    project_id: str
    scope: str
    subject: str
    predicate: str
    value: str
    source: SourceInput
    fact_id: str | None = None
    expected_revision: int | None = None

    def __post_init__(self):
        for name in ("project_id", "scope", "subject", "predicate"):
            identifier(getattr(self, name), name)
        if not isinstance(self.source, SourceInput):
            raise ValidationError("source is required")
        if self.fact_id is not None:
            identifier(self.fact_id, "fact_id")
        text(self.value, "value")
        revision(self.expected_revision)


@dataclass(frozen=True)
class UpdateInput:
    project_id: str
    scope: str
    event_id: str
    text: str
    source: SourceInput
    classification: str
    confirmation: bool = False
    candidate: Candidate | None = None
    target_fact_id: str | None = None
    replacement_fact_id: str | None = None
    expected_revision: int | None = None

    def __post_init__(self):
        for name in ("project_id", "scope", "event_id"):
            identifier(getattr(self, name), name)
        for name in ("target_fact_id", "replacement_fact_id"):
            if getattr(self, name) is not None:
                identifier(getattr(self, name), name)
        text(self.text, "text", 16000)
        if not isinstance(self.source, SourceInput):
            raise ValidationError("source is required")
        if self.candidate is not None and not isinstance(self.candidate, Candidate):
            raise ValidationError("candidate must be a Candidate")
        if self.classification not in ("confirmed_change", "proposal", "ambiguous", "unrelated"):
            raise ValidationError("Unknown classification")
        if type(self.confirmation) is not bool:
            raise ValidationError("confirmation must be a JSON boolean")
        if self.candidate and self.candidate.excerpt not in self.source.content:
            raise ValidationError("candidate.excerpt must occur verbatim in source.content")
        revision(self.expected_revision)


@dataclass(frozen=True)
class NaturalUpdateInput:
    """Natural-language replacement of one explicitly selected scoped key."""

    project_id: str
    scope: str
    subject: str
    predicate: str
    event_id: str
    text: str
    source: SourceInput
    confirmation: bool = False
    expected_revision: int | None = None

    def __post_init__(self):
        for name in ("project_id", "scope", "subject", "predicate", "event_id"):
            identifier(getattr(self, name), name)
        text(self.text, "text", 4000)
        if not isinstance(self.source, SourceInput):
            raise ValidationError("source is required")
        text(self.source.content, "source.content", 6000)
        if type(self.confirmation) is not bool:
            raise ValidationError("confirmation must be a JSON boolean")
        revision(self.expected_revision)


@dataclass(frozen=True)
class PlanInput:
    project_id: str
    scope: str
    text: str
    dependency_fact_ids: list[str]
    plan_id: str | None = None
    expected_revision: int | None = None

    def __post_init__(self):
        identifier(self.project_id, "project_id")
        identifier(self.scope, "scope")
        text(self.text, "text", 4000)
        if self.plan_id is not None:
            identifier(self.plan_id, "plan_id")
        if not isinstance(self.dependency_fact_ids, list) or len(self.dependency_fact_ids) > 32:
            raise ValidationError("dependency_fact_ids must be a list of at most 32 IDs")
        for item in self.dependency_fact_ids:
            identifier(item, "dependency fact ID")
        if len(set(self.dependency_fact_ids)) != len(self.dependency_fact_ids):
            raise ValidationError("Duplicate dependency IDs")
        revision(self.expected_revision)


def data(value: Any) -> dict:
    return asdict(value)
