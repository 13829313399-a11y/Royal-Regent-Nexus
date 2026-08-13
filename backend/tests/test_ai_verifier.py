from datetime import UTC, datetime

import pytest
from app.schemas.ai import AIEvidenceReferenceV1, AIEvidenceSourceLevel
from app.services.ai.verifier import (
    AIFactStatus,
    AIVerificationClaim,
    AIVerificationError,
    verify_claim,
)


def _evidence(
    evidence_id: str,
    *,
    factory_id: str = "huaxing",
    source_level: AIEvidenceSourceLevel = (
        AIEvidenceSourceLevel.FORMAL_DOMAIN_SERVICE
    ),
    truncated: bool = False,
) -> AIEvidenceReferenceV1:
    return AIEvidenceReferenceV1(
        evidence_id=evidence_id,
        source_level=source_level,
        source_name="injection_scheduling.get_plan_context",
        factory_id=factory_id,
        as_of=datetime(2026, 8, 12, tzinfo=UTC),
        content_hash=f"sha256:{'b' * 64}",
        truncated=truncated,
    )


def _claim(**overrides: object) -> AIVerificationClaim:
    values: dict[str, object] = {
        "claim_id": "claim:formal-plan",
        "critical_formal": True,
        "factory_id": "huaxing",
        "evidence_ids": ("ev:formal-1",),
        "asserted_status": AIFactStatus.PUBLISHED,
        "observed_status": AIFactStatus.PUBLISHED,
        "tool_succeeded": True,
    }
    values.update(overrides)
    return AIVerificationClaim.model_validate(values)


def test_formal_claim_with_matching_evidence_passes() -> None:
    verify_claim(_claim(), (_evidence("ev:formal-1"),))


@pytest.mark.parametrize(
    ("claim", "evidence", "message"),
    [
        (_claim(evidence_ids=()), (), "requires Evidence"),
        (
            _claim(evidence_ids=("ev:missing",)),
            (_evidence("ev:formal-1"),),
            "unknown Evidence",
        ),
        (
            _claim(observed_status=AIFactStatus.DRAFT),
            (_evidence("ev:formal-1"),),
            "DRAFT",
        ),
        (
            _claim(
                asserted_status=AIFactStatus.EXECUTED,
                observed_status=AIFactStatus.PREVIEW,
            ),
            (_evidence("ev:formal-1"),),
            "Preview",
        ),
        (
            _claim(asserts_complete=True),
            (_evidence("ev:formal-1", truncated=True),),
            "truncated",
        ),
        (
            _claim(tool_succeeded=False),
            (_evidence("ev:formal-1"),),
            "failed Tool",
        ),
    ],
)
def test_verifier_blocks_unsupported_status_completeness_and_failures(
    claim: AIVerificationClaim,
    evidence: tuple[AIEvidenceReferenceV1, ...],
    message: str,
) -> None:
    with pytest.raises(AIVerificationError, match=message):
        verify_claim(claim, evidence)


def test_cross_factory_requires_grouping_and_user_file_is_not_formal() -> None:
    mixed = (
        _evidence("ev:formal-1"),
        _evidence("ev:formal-2", factory_id="huakang-b"),
    )
    with pytest.raises(AIVerificationError, match="cross-factory"):
        verify_claim(
            _claim(
                factory_id=None,
                evidence_ids=("ev:formal-1", "ev:formal-2"),
            ),
            mixed,
        )
    verify_claim(
        _claim(
            factory_id=None,
            grouped_by_factory=True,
            evidence_ids=("ev:formal-1", "ev:formal-2"),
        ),
        mixed,
    )

    user_file = _evidence(
        "ev:user-file",
        source_level=AIEvidenceSourceLevel.USER_PROVIDED,
    )
    with pytest.raises(AIVerificationError, match="lacks formal Evidence"):
        verify_claim(
            _claim(evidence_ids=("ev:user-file",)),
            (user_file,),
        )
