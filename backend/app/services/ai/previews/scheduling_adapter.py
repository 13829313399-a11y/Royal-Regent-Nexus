from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from app.models.injection_scheduling_execution import InjectionSchedulingPlan
from app.models.injection_scheduling_scheduler import InjectionSchedulingRun
from app.schemas.ai.evidence import AIEvidenceReferenceV1, AIEvidenceSourceLevel
from app.schemas.ai.preview import (
    AIPreviewAssumption,
    AIPreviewManifestV1,
    AIPreviewStatus,
    AIScenarioCompareContractV1,
)
from app.services.ai.previews.registry import build_preview_registry
from app.services.ai.previews.verifier import (
    PreviewVerificationContext,
    verify_preview,
)
from app.services.auth import AuthContext


def _canonical_hash(value: object) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def scheduling_source_revision_hash(
    *,
    plan_id: str,
    plan_revision: int,
    rule_revision: int,
    input_snapshot_json: str,
    horizon_start: str,
    horizon_end: str,
) -> str:
    try:
        snapshot = json.loads(input_snapshot_json)
    except json.JSONDecodeError:
        snapshot = {"invalid_snapshot": True}
    return _canonical_hash(
        {
            "plan_id": plan_id,
            "plan_revision": plan_revision,
            "rule_revision": rule_revision,
            "input_snapshot_hash": _canonical_hash(snapshot),
            "horizon_start": horizon_start,
            "horizon_end": horizon_end,
        }
    )


def _current_revision_hash(
    record: InjectionSchedulingRun,
    *,
    current_plan: InjectionSchedulingPlan | object | None,
    current_rule_revision: int | None,
) -> str:
    if current_plan is None or current_rule_revision is None:
        return "0" * 64
    return scheduling_source_revision_hash(
        plan_id=str(getattr(current_plan, "id", "")),
        plan_revision=int(getattr(current_plan, "revision", 0)),
        rule_revision=current_rule_revision,
        input_snapshot_json=record.input_snapshot_json,
        horizon_start=record.horizon_start,
        horizon_end=record.horizon_end,
    )


def build_scheduling_preview_manifest(
    record: InjectionSchedulingRun,
    *,
    user: AuthContext,
    current_plan: InjectionSchedulingPlan | object | None,
    current_rule_revision: int | None,
    ttl_minutes: int,
    now: datetime,
) -> AIPreviewManifestV1:
    created_at = datetime.fromisoformat(record.created_at)
    source_hash = scheduling_source_revision_hash(
        plan_id=record.plan_id,
        plan_revision=record.expected_plan_revision,
        rule_revision=record.rule_revision,
        input_snapshot_json=record.input_snapshot_json,
        horizon_start=record.horizon_start,
        horizon_end=record.horizon_end,
    )
    evidence = AIEvidenceReferenceV1(
        evidence_id=f"preview:{_canonical_hash(record.id)[:24]}",
        source_level=AIEvidenceSourceLevel.FORMAL_DOMAIN_SERVICE,
        source_name="injection_scheduling.preview_run",
        factory_id=record.factory_id,
        as_of=created_at,
        entity_type="scheduling_preview_run",
        entity_id=record.id,
        entity_revision=record.revision,
        content_hash=f"sha256:{source_hash}",
    )
    initial = AIPreviewManifestV1(
        preview_id=record.id,
        preview_type="injection_scheduling.run",
        source_revision_hash=source_hash,
        factory_id=record.factory_id,
        input_hash=record.payload_hash,
        assumptions=(
            AIPreviewAssumption(
                key="plan_status",
                label="计划切片",
                value="DRAFT",
            ),
            AIPreviewAssumption(
                key="preview_mode",
                label="运行模式",
                value="PREVIEW",
            ),
            AIPreviewAssumption(
                key="candidate_state",
                label="候选状态",
                value="尚未应用、发布或执行",
            ),
            AIPreviewAssumption(
                key="result_origin",
                label="结果来源",
                value="现有注塑排产确定性 Service",
            ),
        ),
        evidence_refs=(evidence,),
        created_by=record.created_by,
        created_at=created_at,
        expires_at=created_at + timedelta(minutes=ttl_minutes),
        status=AIPreviewStatus.READY,
        deterministic_service=True,
        can_propose_action=False,
    )
    current_hash = _current_revision_hash(
        record,
        current_plan=current_plan,
        current_rule_revision=current_rule_revision,
    )
    verification = verify_preview(
        initial,
        registry=build_preview_registry(),
        context=PreviewVerificationContext(
            user=user,
            factory_id=record.factory_id,
            current_source_revision_hash=current_hash,
            now=now,
        ),
    )
    return AIPreviewManifestV1.model_validate(
        {
            **initial.model_dump(mode="python"),
            "status": verification.status,
            "can_propose_action": verification.can_propose_action,
            "action_capability": (
                "CREATE_PROPOSAL_ONLY"
                if verification.can_propose_action
                else None
            ),
        }
    )


def build_scheduling_scenario_compare(
    manifests: tuple[AIPreviewManifestV1, ...],
    *,
    warning: str,
) -> AIScenarioCompareContractV1:
    hashes = tuple(dict.fromkeys(item.source_revision_hash for item in manifests))
    comparable = len(hashes) == 1
    return AIScenarioCompareContractV1(
        preview_type="injection_scheduling.run",
        preview_ids=tuple(item.preview_id for item in manifests),
        source_revision_hashes=hashes,
        comparable=comparable,
        comparison_basis=(
            "SAME_SOURCE_REVISION" if comparable else "MIXED_SOURCE_REVISION"
        ),
        warning=warning,
    )
