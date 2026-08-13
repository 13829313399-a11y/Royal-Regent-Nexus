from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from app.schemas.ai.evidence import AIEvidenceReferenceV1
from app.schemas.ai.scheduling import AIInjectionSchedulingBacklogData
from app.schemas.ai.vision_observation import (
    AIVisionComparisonData,
    AIVisionComparisonRow,
    AIVisionFieldComparison,
    AIVisionObservationData,
    AIVisionObservationRow,
)

LOW_CONFIDENCE_THRESHOLD = 0.8


def _normalized_date(value: str) -> str | None:
    normalized = value.replace("/", "-").replace(".", "-")
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError:
        return None


def _normalized_quantity(value: str) -> Decimal | None:
    try:
        return Decimal(value.replace(",", ""))
    except InvalidOperation:
        return None


def _field_comparisons(
    row: AIVisionObservationRow,
    formal,
) -> tuple[AIVisionFieldComparison, ...]:
    values = (
        (
            "mold_no",
            row.mold_no,
            str(formal.mold_no),
            row.mold_no_confidence,
            lambda value: value,
        ),
        (
            "delivery_due_date",
            row.delivery_due_date,
            str(formal.delivery_due_date),
            row.delivery_due_date_confidence,
            _normalized_date,
        ),
        (
            "outstanding_quantity",
            row.outstanding_quantity,
            str(formal.outstanding_quantity),
            row.outstanding_quantity_confidence,
            _normalized_quantity,
        ),
    )
    result: list[AIVisionFieldComparison] = []
    for field_name, observed, formal_value, confidence, normalizer in values:
        if (
            observed is None
            or confidence < LOW_CONFIDENCE_THRESHOLD
            or field_name in row.uncertain_fields
        ):
            status = "UNCONFIRMED"
        else:
            left = normalizer(observed)
            right = normalizer(formal_value)
            status = "SAME" if left is not None and left == right else "DIFFERENT"
        result.append(
            AIVisionFieldComparison(
                field=field_name,
                observed=observed,
                formal=formal_value,
                status=status,
            )
        )
    return tuple(result)


def compare_observation_to_formal_backlog(
    *,
    observation_task_id: str,
    observation_data: AIVisionObservationData,
    observation_evidence: AIEvidenceReferenceV1,
    formal_backlog: AIInjectionSchedulingBacklogData,
) -> AIVisionComparisonData:
    """Deterministically compare exact order/item strings; never derive Tool arguments."""

    formal_by_key: dict[tuple[str, str], list[object]] = {}
    for item in formal_backlog.items:
        formal_by_key.setdefault((item.order_no, item.item_no), []).append(item)

    rows: list[AIVisionComparisonRow] = []
    matched_formal_ids: set[str] = set()
    for observed in observation_data.observation.rows:
        if observed.order_no is None or observed.item_no is None:
            rows.append(
                AIVisionComparisonRow(
                    status="UNCONFIRMED",
                    observation=observed,
                    formal=None,
                    reason_code="MISSING_MATCH_KEY",
                )
            )
            continue
        if (
            observed.row_confidence < LOW_CONFIDENCE_THRESHOLD
            or observed.order_no_confidence < LOW_CONFIDENCE_THRESHOLD
            or observed.item_no_confidence < LOW_CONFIDENCE_THRESHOLD
            or "order_no" in observed.uncertain_fields
            or "item_no" in observed.uncertain_fields
        ):
            rows.append(
                AIVisionComparisonRow(
                    status="UNCONFIRMED",
                    observation=observed,
                    formal=None,
                    reason_code="LOW_CONFIDENCE",
                )
            )
            continue
        candidates = formal_by_key.get((observed.order_no, observed.item_no), [])
        if not candidates:
            rows.append(
                AIVisionComparisonRow(
                    status="IMAGE_ONLY",
                    observation=observed,
                    formal=None,
                    reason_code="NOT_IN_RETURNED_FORMAL_PAGE",
                )
            )
            continue
        if len(candidates) != 1:
            rows.append(
                AIVisionComparisonRow(
                    status="UNCONFIRMED",
                    observation=observed,
                    formal=None,
                    reason_code="AMBIGUOUS_FORMAL_MATCH",
                )
            )
            continue
        formal = candidates[0]
        comparisons = _field_comparisons(observed, formal)
        matched_formal_ids.add(formal.order_id)
        if any(item.status == "DIFFERENT" for item in comparisons):
            row_status = "DIFFERENT"
            reason_code = "FIELD_DIFFERENCE"
        elif any(item.status == "UNCONFIRMED" for item in comparisons):
            row_status = "UNCONFIRMED"
            reason_code = "LOW_CONFIDENCE"
        else:
            row_status = "MATCHED"
            reason_code = "EXACT_ORDER_ITEM_MATCH"
        rows.append(
            AIVisionComparisonRow(
                status=row_status,
                observation=observed,
                formal=formal,
                field_comparisons=comparisons,
                reason_code=reason_code,
            )
        )

    for formal in formal_backlog.items:
        if formal.order_id not in matched_formal_ids:
            rows.append(
                AIVisionComparisonRow(
                    status="FORMAL_ONLY",
                    observation=None,
                    formal=formal,
                    reason_code="NOT_IN_IMAGE_OBSERVATION",
                )
            )

    counts = {
        status: sum(item.status == status for item in rows)
        for status in (
            "MATCHED",
            "DIFFERENT",
            "UNCONFIRMED",
            "IMAGE_ONLY",
            "FORMAL_ONLY",
        )
    }
    return AIVisionComparisonData(
        factory_id=formal_backlog.factory_id,
        observation_task_id=observation_task_id,
        source_artifact_id=observation_data.source_artifact_id,
        source_sha256=observation_data.source_sha256,
        observation_evidence=observation_evidence,
        observation=observation_data.observation,
        formal_backlog=formal_backlog,
        comparison_rows=tuple(rows),
        matched_count=counts["MATCHED"],
        different_count=counts["DIFFERENT"],
        unconfirmed_count=counts["UNCONFIRMED"],
        image_only_count=counts["IMAGE_ONLY"],
        formal_only_count=counts["FORMAL_ONLY"],
    )
