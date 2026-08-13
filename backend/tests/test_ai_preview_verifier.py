from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.schemas.ai.evidence import AIEvidenceReferenceV1, AIEvidenceSourceLevel
from app.schemas.ai.preview import (
    AIPreviewAssumption,
    AIPreviewManifestV1,
    AIPreviewStatus,
)
from app.services.ai.previews.registry import PreviewRegistry, build_preview_registry
from app.services.ai.previews.scheduling_adapter import (
    build_scheduling_scenario_compare,
)
from app.services.ai.previews.verifier import (
    PreviewVerificationContext,
    verify_preview,
)
from app.services.ai.task_runner import _safe_tool_metadata
from app.services.auth import AuthContext, AuthGrantContext

NOW = datetime(2026, 8, 13, 0, 30, tzinfo=UTC)
SOURCE_HASH = "a" * 64


def _user(*, permitted: bool = True, cross_factory: bool = False) -> AuthContext:
    permissions = (
        frozenset({"injection_scheduling:edit"}) if permitted else frozenset()
    )
    factories = ("huaxing", "huakang-a") if cross_factory else ("huaxing",)
    grants = tuple(
        AuthGrantContext(
            role_id=f"preview-role-{factory}",
            role_name="Preview Reviewer",
            role_code="preview_reviewer",
            factory_id=factory,
            department="production",
            permissions=permissions,
            binding_id=f"preview-binding-{factory}",
        )
        for factory in factories
    )
    return AuthContext(
        id="preview-reviewer",
        username="preview-reviewer",
        display_name="Preview Reviewer",
        roles=("Preview Reviewer",),
        role_codes=("preview_reviewer",),
        permissions=permissions,
        factory_scopes=factories,
        department_scopes=("production",),
        grants=grants,
        active_permission_codes=permissions,
    )


def _manifest(*, plan_status: str = "DRAFT") -> AIPreviewManifestV1:
    return AIPreviewManifestV1(
        preview_id="isrun-preview-verifier-1",
        preview_type="injection_scheduling.run",
        source_revision_hash=SOURCE_HASH,
        factory_id="huaxing",
        input_hash="b" * 64,
        assumptions=(
            AIPreviewAssumption(
                key="plan_status", label="计划切片", value=plan_status
            ),
            AIPreviewAssumption(
                key="preview_mode", label="运行模式", value="PREVIEW"
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
        evidence_refs=(
            AIEvidenceReferenceV1(
                evidence_id="preview:formal:test",
                source_level=AIEvidenceSourceLevel.FORMAL_DOMAIN_SERVICE,
                source_name="injection_scheduling.preview_run",
                factory_id="huaxing",
                as_of=NOW,
                content_hash=f"sha256:{SOURCE_HASH}",
            ),
        ),
        created_by="preview-reviewer",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
        status=AIPreviewStatus.READY,
        deterministic_service=True,
        can_propose_action=True,
        action_capability="CREATE_PROPOSAL_ONLY",
    )


def _verify(
    manifest: AIPreviewManifestV1,
    *,
    user: AuthContext | None = None,
    factory_id: str = "huaxing",
    source_hash: str = SOURCE_HASH,
    now: datetime = NOW,
    registry: PreviewRegistry | None = None,
):
    return verify_preview(
        manifest,
        registry=registry or build_preview_registry(),
        context=PreviewVerificationContext(
            user=user or _user(),
            factory_id=factory_id,
            current_source_revision_hash=source_hash,
            now=now,
        ),
    )


def test_ready_preview_only_allows_creating_a_proposal_not_direct_execution() -> None:
    result = _verify(_manifest())

    assert result.status is AIPreviewStatus.READY
    assert result.reason_codes == ()
    assert result.can_propose_action is True
    assert _manifest().action_capability == "CREATE_PROPOSAL_ONLY"
    assert _manifest().no_write_performed is True


def test_stale_expired_revoked_and_cross_factory_previews_fail_closed() -> None:
    stale = _verify(_manifest(), source_hash="c" * 64)
    assert stale.status is AIPreviewStatus.STALE
    assert stale.reason_codes == ("PREVIEW_SOURCE_STALE",)
    assert stale.can_propose_action is False

    expired = _verify(_manifest(), now=NOW + timedelta(minutes=31))
    assert expired.status is AIPreviewStatus.EXPIRED
    assert "PREVIEW_EXPIRED" in expired.reason_codes

    revoked = _verify(_manifest(), user=_user(permitted=False))
    assert revoked.status is AIPreviewStatus.ACCESS_REVOKED
    assert revoked.can_propose_action is False

    cross_factory = _verify(
        _manifest(),
        user=_user(cross_factory=True),
        factory_id="huakang-a",
    )
    assert cross_factory.status is AIPreviewStatus.INVALID
    assert "PREVIEW_FACTORY_MISMATCH" in cross_factory.reason_codes


def test_draft_published_confusion_and_unregistered_types_are_invalid() -> None:
    mislabeled = _verify(_manifest(plan_status="PUBLISHED"))
    assert mislabeled.status is AIPreviewStatus.INVALID
    assert "PREVIEW_ASSUMPTIONS_INVALID" in mislabeled.reason_codes

    unregistered = _verify(_manifest(), registry=PreviewRegistry(()))
    assert unregistered.status is AIPreviewStatus.INVALID
    assert unregistered.reason_codes == ("PREVIEW_TYPE_UNREGISTERED",)


def test_task_metadata_persists_bounded_preview_manifest_and_evidence() -> None:
    manifest = _manifest()
    outcome = SimpleNamespace(
        provider_output_json=json.dumps(
            {
                "data": {
                    "result_type": "injection_scheduling.preview_run",
                    "run": {"preview_manifest": manifest.model_dump(mode="json")},
                },
                "evidence": [
                    manifest.evidence_refs[0].model_dump(mode="json")
                ],
            }
        ),
        tool_name="injection_scheduling.generate_preview",
        row_count=1,
        field_count=12,
        byte_count=2048,
        truncated=False,
    )

    metadata, evidence, artifacts = _safe_tool_metadata(outcome)

    assert metadata["preview_manifests"][0]["status"] == "READY"
    assert metadata["preview_manifests"][0]["can_propose_action"] is True
    assert len(evidence) == 1
    assert evidence[0].source_level is AIEvidenceSourceLevel.FORMAL_DOMAIN_SERVICE
    assert artifacts == ()


def test_scenario_compare_contract_uses_source_revisions_and_never_writes() -> None:
    first = _manifest()
    same_source = first.model_copy(update={"preview_id": "isrun-preview-verifier-2"})
    comparable = build_scheduling_scenario_compare(
        (first, same_source),
        warning="同一来源版本，可直接比较。",
    )
    assert comparable.comparable is True
    assert comparable.comparison_basis == "SAME_SOURCE_REVISION"
    assert comparable.no_write_performed is True

    mixed_source = first.model_copy(
        update={
            "preview_id": "isrun-preview-verifier-3",
            "source_revision_hash": "c" * 64,
        }
    )
    incomparable = build_scheduling_scenario_compare(
        (first, mixed_source),
        warning="来源版本不同，不可直接比较。",
    )
    assert incomparable.comparable is False
    assert incomparable.comparison_basis == "MIXED_SOURCE_REVISION"
    assert incomparable.source_revision_hashes == (SOURCE_HASH, "c" * 64)
