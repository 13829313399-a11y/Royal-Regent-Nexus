from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from app.schemas.ai.evidence import AIEvidenceReferenceV1, AIEvidenceSourceLevel
from app.schemas.ai.preview import (
    AIPreviewAssumption,
    AIPreviewManifestV1,
    AIPreviewStatus,
)
from app.schemas.ai.workbook import AIWorkbookSemanticSnapshot
from app.services.ai.previews.registry import build_preview_registry
from app.services.ai.previews.verifier import (
    PreviewVerificationContext,
    verify_preview,
)
from app.services.auth import AuthContext


def _canonical_hash(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def workbook_mapping_source_revision_hash(
    *,
    snapshot: AIWorkbookSemanticSnapshot,
    profile_definition_sha256: str,
) -> str:
    return _canonical_hash(
        {
            "source_sha256": snapshot.source_lineage.source_sha256,
            "snapshot_sha256": snapshot.snapshot_sha256,
            "inspector_version": snapshot.source_lineage.inspector_version,
            "profile_definition_sha256": profile_definition_sha256,
        }
    )

def build_workbook_mapping_manifest(
    *,
    snapshot: AIWorkbookSemanticSnapshot,
    document_kind: str,
    generated_by_model: str,
    mapping_result: object,
    profile_definition_sha256: str,
    user: AuthContext,
    ttl_minutes: int,
    now: datetime,
) -> AIPreviewManifestV1:
    source_hash = workbook_mapping_source_revision_hash(
        snapshot=snapshot,
        profile_definition_sha256=profile_definition_sha256,
    )
    input_hash = _canonical_hash(
        {
            "document_kind": document_kind,
            "source_revision_hash": source_hash,
        }
    )
    result_hash = _canonical_hash(mapping_result)
    preview_id = f"aiprv-{input_hash[:32]}"
    user_evidence = AIEvidenceReferenceV1(
        evidence_id=f"preview:{input_hash[:24]}",
        source_level=AIEvidenceSourceLevel.USER_PROVIDED,
        source_name="workbook.semantic_snapshot",
        factory_id=snapshot.factory_id,
        as_of=now,
        entity_type=(
            "ai_artifact" if snapshot.source_lineage.artifact_id is not None else None
        ),
        entity_id=snapshot.source_lineage.artifact_id,
        content_hash=f"sha256:{source_hash}",
    )
    inference_evidence = AIEvidenceReferenceV1(
        evidence_id=f"preview:{result_hash[:24]}",
        source_level=AIEvidenceSourceLevel.MODEL_INFERENCE,
        source_name="workbook.mapping_proposal",
        factory_id=snapshot.factory_id,
        as_of=now,
        content_hash=f"sha256:{result_hash}",
    )
    initial = AIPreviewManifestV1(
        preview_id=preview_id,
        preview_type="workbook.mapping",
        source_revision_hash=source_hash,
        factory_id=snapshot.factory_id,
        input_hash=input_hash,
        assumptions=(
            AIPreviewAssumption(
                key="target_status",
                label="目标状态",
                value="PROFILE_DRAFT",
            ),
            AIPreviewAssumption(
                key="approval_required",
                label="人工审核",
                value="必须完成",
            ),
            AIPreviewAssumption(
                key="source_authority",
                label="建议权威性",
                value=f"MODEL_INFERENCE:{generated_by_model}",
            ),
            AIPreviewAssumption(
                key="write_performed",
                label="业务写入",
                value="未执行",
            ),
        ),
        evidence_refs=(user_evidence, inference_evidence),
        created_by=user.id,
        created_at=now,
        expires_at=now + timedelta(minutes=ttl_minutes),
        status=AIPreviewStatus.READY,
        deterministic_service=False,
        can_propose_action=False,
    )
    verification = verify_preview(
        initial,
        registry=build_preview_registry(),
        context=PreviewVerificationContext(
            user=user,
            factory_id=snapshot.factory_id,
            current_source_revision_hash=source_hash,
            now=now,
        ),
    )
    return AIPreviewManifestV1.model_validate(
        {
            **initial.model_dump(mode="python"),
            "status": verification.status,
            "can_propose_action": False,
            "action_capability": None,
        }
    )
