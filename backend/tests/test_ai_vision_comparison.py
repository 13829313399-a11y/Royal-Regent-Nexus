from __future__ import annotations

from datetime import UTC, datetime

from app.schemas.ai.evidence import AIEvidenceReferenceV1, AIEvidenceSourceLevel
from app.schemas.ai.vision_observation import (
    AIVisionObservationData,
    AIVisionObservationRow,
    AIVisionProviderObservation,
)
from app.services.ai.serializers.scheduling import serialize_backlog_page
from app.services.ai.vision_comparison import compare_observation_to_formal_backlog
from app.services.injection_scheduling_execution import (
    InjectionSchedulingAIBacklogOrder,
    InjectionSchedulingAIBacklogPage,
)

ARTIFACT_ID = f"aiart-{'a' * 32}"
ARTIFACT_SHA = "b" * 64
TASK_ID = f"aitask-{'c' * 32}"


def _row(
    *,
    row_index: int,
    order_no: str | None,
    item_no: str | None,
    row_confidence: float = 0.95,
    mold_no: str | None = "M-001",
    mold_no_confidence: float = 0.95,
    delivery_due_date: str | None = "2026-08-31",
    delivery_due_date_confidence: float = 0.95,
    outstanding_quantity: str | None = "00120.00",
    outstanding_quantity_confidence: float = 0.95,
) -> AIVisionObservationRow:
    return AIVisionObservationRow(
        row_index=row_index,
        order_no=order_no,
        order_no_confidence=0.95 if order_no is not None else 0,
        item_no=item_no,
        item_no_confidence=0.95 if item_no is not None else 0,
        mold_no=mold_no,
        mold_no_confidence=mold_no_confidence,
        delivery_due_date=delivery_due_date,
        delivery_due_date_confidence=delivery_due_date_confidence,
        outstanding_quantity=outstanding_quantity,
        outstanding_quantity_confidence=outstanding_quantity_confidence,
        row_confidence=row_confidence,
    )


def _observation(*rows: AIVisionObservationRow) -> AIVisionObservationData:
    return AIVisionObservationData(
        factory_id="huaxing",
        source_artifact_id=ARTIFACT_ID,
        source_sha256=ARTIFACT_SHA,
        as_of="2026-08-12T08:00:00+00:00",
        provider="qwen",
        model="qwen3.7-plus",
        observation=AIVisionProviderObservation(
            overall_confidence=0.91,
            instructions_detected=False,
            unreadable_region_count=0,
            rows=rows,
        ),
    )


def _formal_order(
    *,
    order_id: str,
    order_no: str,
    item_no: str,
    mold_no: str = "M-001",
    delivery_due_date: str = "2026-08-31",
    outstanding_quantity: float = 120,
) -> InjectionSchedulingAIBacklogOrder:
    return InjectionSchedulingAIBacklogOrder(
        order_id=order_id,
        order_no=order_no,
        item_no=item_no,
        product_name="测试产品",
        mold_no=mold_no,
        priority_code="NORMAL",
        delivery_due_date=delivery_due_date,
        order_quantity=200,
        outstanding_quantity=outstanding_quantity,
        mold_enrichment_status="MATCHED",
        source_type="DEMAND_ORDER",
    )


def _formal(*items: InjectionSchedulingAIBacklogOrder, total: int | None = None):
    return serialize_backlog_page(
        InjectionSchedulingAIBacklogPage(
            factory_id="huaxing",
            as_of="2026-08-12T16:30:00+08:00",
            source_scope="GLOBAL_BACKLOG",
            total=len(items) if total is None else total,
            limit=20,
            offset=0,
            items=items,
        )
    )


def _evidence() -> AIEvidenceReferenceV1:
    return AIEvidenceReferenceV1(
        evidence_id="vision:observation:test",
        source_level=AIEvidenceSourceLevel.USER_PROVIDED,
        source_name="vision.observe_injection_backlog_image",
        factory_id="huaxing",
        as_of=datetime(2026, 8, 12, 8, tzinfo=UTC),
        content_hash=f"sha256:{ARTIFACT_SHA}",
    )


def test_comparison_is_exact_deterministic_and_keeps_evidence_separate() -> None:
    observed = _observation(
        _row(row_index=1, order_no="00123", item_no="0007", mold_no="M-IMAGE"),
        _row(
            row_index=2,
            order_no="00999",
            item_no="0001",
            row_confidence=0.70,
        ),
        _row(row_index=3, order_no=None, item_no="0002"),
        _row(row_index=4, order_no="00888", item_no="0003"),
    )
    formal = _formal(
        _formal_order(
            order_id="order-formal-1",
            order_no="00123",
            item_no="0007",
            mold_no="M-FORMAL",
        ),
        _formal_order(
            order_id="order-formal-2",
            order_no="00999",
            item_no="0001",
        ),
        _formal_order(
            order_id="order-formal-3",
            order_no="123",
            item_no="0007",
        ),
        total=30,
    )

    result = compare_observation_to_formal_backlog(
        observation_task_id=TASK_ID,
        observation_data=observed,
        observation_evidence=_evidence(),
        formal_backlog=formal,
    )

    assert result.source_type == "FORMAL"
    assert result.observation_evidence.source_level is AIEvidenceSourceLevel.USER_PROVIDED
    assert result.formal_backlog.source_type == "FORMAL"
    assert result.formal_backlog.as_of == "2026-08-12T16:30:00+08:00"
    assert result.formal_backlog.truncated is True
    assert result.no_write_performed is True
    assert result.different_count == 1
    assert result.unconfirmed_count == 2
    assert result.image_only_count == 1
    assert result.formal_only_count == 2
    different = next(row for row in result.comparison_rows if row.status == "DIFFERENT")
    assert different.observation is not None
    assert different.observation.order_no == "00123"
    assert different.formal is not None
    assert different.formal.order_no == "00123"
    assert next(
        field for field in different.field_comparisons if field.field == "mold_no"
    ).status == "DIFFERENT"
    assert any(
        row.status == "FORMAL_ONLY"
        and row.formal is not None
        and row.formal.order_no == "123"
        for row in result.comparison_rows
    )


def test_low_confidence_fields_are_unconfirmed_instead_of_guessed() -> None:
    observed = _observation(
        _row(
            row_index=1,
            order_no="00123",
            item_no="0007",
            outstanding_quantity="120",
            outstanding_quantity_confidence=0.79,
        )
    )
    formal = _formal(
        _formal_order(
            order_id="order-formal-1",
            order_no="00123",
            item_no="0007",
        )
    )

    result = compare_observation_to_formal_backlog(
        observation_task_id=TASK_ID,
        observation_data=observed,
        observation_evidence=_evidence(),
        formal_backlog=formal,
    )

    assert result.unconfirmed_count == 1
    row = result.comparison_rows[0]
    assert row.reason_code == "LOW_CONFIDENCE"
    assert next(
        field
        for field in row.field_comparisons
        if field.field == "outstanding_quantity"
    ).status == "UNCONFIRMED"
