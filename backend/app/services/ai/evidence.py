from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime

from app.schemas.ai import (
    AIEvidenceReferenceV1,
    AIEvidenceSourceLevel,
    AIServerPageContext,
)
from app.services.ai.tool_registry import ToolAccessContext, ToolRegistry, ToolSpec


class EvidenceError(ValueError):
    """Evidence metadata failed closed validation."""


def _canonical_hash(value: object) -> str:
    try:
        serialized = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise EvidenceError("Evidence content is not canonical JSON") from exc
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"


def _aware_as_of(value: object) -> datetime:
    if isinstance(value, datetime):
        candidate = value
    elif isinstance(value, str):
        try:
            candidate = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise EvidenceError("Evidence source time is invalid") from exc
    else:
        return datetime.now(UTC)
    if candidate.tzinfo is None or candidate.utcoffset() is None:
        raise EvidenceError("Evidence source time must include a timezone")
    return candidate


def _source_level(spec: ToolSpec, data: Mapping[str, object]) -> AIEvidenceSourceLevel:
    source_type = data.get("source_type")
    if source_type == "FORMAL":
        return AIEvidenceSourceLevel.FORMAL_DOMAIN_SERVICE
    if source_type in {"MODULE_KNOWLEDGE", "VERSIONED_MODULE_KNOWLEDGE"}:
        return AIEvidenceSourceLevel.VERSIONED_MODULE_KNOWLEDGE
    if source_type == "USER_PROVIDED":
        return AIEvidenceSourceLevel.USER_PROVIDED
    if source_type == "MODEL_INFERENCE":
        return AIEvidenceSourceLevel.MODEL_INFERENCE
    if spec.tool_group in {"identity", "module_knowledge"}:
        return AIEvidenceSourceLevel.AUTHENTICATED_SERVER_CONTEXT
    raise EvidenceError("Tool result has no reviewed Evidence source level")


def _optional_string(
    data: Mapping[str, object],
    name: str,
    *,
    max_length: int,
) -> str | None:
    value = data.get(name)
    if value is None:
        return None
    if not isinstance(value, str) or not value or len(value) > max_length:
        raise EvidenceError(f"Evidence {name} is invalid")
    return value


def build_tool_evidence(
    *,
    spec: ToolSpec,
    request_id: str,
    call_id: str,
    data: object,
    factory_id: str | None,
    truncated: bool,
) -> AIEvidenceReferenceV1:
    if not isinstance(data, Mapping):
        raise EvidenceError("Tool Evidence requires a closed object result")
    content_hash = _canonical_hash(data)
    level = _source_level(spec, data)
    if level is AIEvidenceSourceLevel.FORMAL_DOMAIN_SERVICE and factory_id is None:
        raise EvidenceError("formal Tool Evidence requires a canonical factory")

    entity_type = _optional_string(data, "entity_type", max_length=120)
    entity_id = _optional_string(data, "entity_id", max_length=160)
    entity_revision = data.get("entity_revision")
    if entity_revision is not None and (
        not isinstance(entity_revision, int)
        or isinstance(entity_revision, bool)
        or entity_revision < 0
    ):
        raise EvidenceError("Evidence entity revision is invalid")
    cursor = data.get("cursor", data.get("next_cursor"))
    if cursor is not None and (
        not isinstance(cursor, str) or not cursor or len(cursor) > 512
    ):
        raise EvidenceError("Evidence cursor is invalid")
    as_of = _aware_as_of(data.get("as_of", data.get("updated_at")))
    evidence_digest = hashlib.sha256(
        f"{request_id}:{call_id}:{spec.name}:{content_hash}".encode()
    ).hexdigest()[:32]
    try:
        return AIEvidenceReferenceV1(
            evidence_id=f"ev:{evidence_digest}",
            source_level=level,
            source_name=spec.name,
            factory_id=factory_id,
            as_of=as_of,
            entity_type=entity_type,
            entity_id=entity_id,
            entity_revision=entity_revision,
            content_hash=content_hash,
            truncated=truncated,
            cursor=cursor,
        )
    except ValueError as exc:
        raise EvidenceError("Tool Evidence contract is invalid") from exc


def reauthorize_evidence_open(
    evidence: AIEvidenceReferenceV1,
    *,
    registry: ToolRegistry,
    context: ToolAccessContext,
) -> bool:
    """Evidence references never grant access; opening reuses current Tool IAM."""

    spec = registry.resolve(evidence.source_name)
    if spec is None or not registry.is_available(spec, context):
        return False
    if evidence.factory_id is None:
        return True
    page_context = context.page_context
    return (
        isinstance(page_context, AIServerPageContext)
        and page_context.verified_factory_id == evidence.factory_id
    )
