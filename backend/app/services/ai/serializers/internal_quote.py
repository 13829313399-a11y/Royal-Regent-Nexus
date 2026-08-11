from __future__ import annotations

from dataclasses import dataclass

from app.schemas.ai.internal_quote import (
    AIInternalQuoteSummaryItem,
    AIInternalQuoteSummaryListData,
    InternalQuoteAINavigationTarget,
    InternalQuoteAIStageCode,
    InternalQuoteAIStatusCode,
)
from app.services.ai.internal_quote_read import InternalQuoteAISummaryPage


@dataclass(frozen=True, slots=True)
class _StatusPolicy:
    status_code: InternalQuoteAIStatusCode
    status_label: str
    stage_code: InternalQuoteAIStageCode
    stage_label: str
    navigation_target: InternalQuoteAINavigationTarget


_UNKNOWN_POLICY = _StatusPolicy(
    status_code="unknown",
    status_label="状态待确认",
    stage_code="UNKNOWN",
    stage_label="请在内部报价台核对",
    navigation_target="collaboration",
)
_STATUS_POLICIES = {
    "drafting": _StatusPolicy(
        "drafting", "协作草稿", "COLLABORATION", "分段协作填写", "collaboration"
    ),
    "section_reviewing": _StatusPolicy(
        "section_reviewing",
        "待分段审核",
        "SECTION_REVIEW",
        "分段审核",
        "collaboration",
    ),
    "pending_review": _StatusPolicy(
        "pending_review",
        "待分段审核",
        "SECTION_REVIEW",
        "分段审核",
        "collaboration",
    ),
    "rejected": _StatusPolicy(
        "rejected", "已退回", "RETURNED", "退回后修正", "collaboration"
    ),
    "ready_for_final_review": _StatusPolicy(
        "ready_for_final_review",
        "待最终提交",
        "FINAL_SUBMISSION",
        "等待提交最终放行",
        "summary",
    ),
    "final_reviewing": _StatusPolicy(
        "final_reviewing",
        "待最终放行",
        "FINAL_REVIEW",
        "等待负责跟客确认放行",
        "summary",
    ),
    "fully_approved": _StatusPolicy(
        "fully_approved", "已放行", "RELEASED", "最终放行已通过", "summary"
    ),
    "exported": _StatusPolicy(
        "exported", "已导出", "EXPORTED", "受控文件已导出", "summary"
    ),
    "archived": _StatusPolicy(
        "archived", "已归档", "ARCHIVED", "报价已归档", "collaboration"
    ),
}


def serialize_internal_quote_summary_page(
    value: object,
) -> AIInternalQuoteSummaryListData:
    if not isinstance(value, InternalQuoteAISummaryPage):
        raise TypeError("internal quote serializer received an unsupported value")
    return AIInternalQuoteSummaryListData(
        factory_id=value.factory_id,
        as_of=value.as_of,
        total=value.total,
        limit=value.limit,
        offset=value.offset,
        returned=len(value.items),
        truncated=value.truncated,
        quotes=[
            AIInternalQuoteSummaryItem(
                quote_id=item.quote_id,
                quote_no=item.quote_no,
                customer=item.customer,
                status_code=(policy := _STATUS_POLICIES.get(
                    item.status,
                    _UNKNOWN_POLICY,
                )).status_code,
                status_label=policy.status_label,
                current_stage_code=policy.stage_code,
                current_stage_label=policy.stage_label,
                version_label=item.version_label,
                updated_at=item.updated_at,
                navigation_target=policy.navigation_target,
            )
            for item in value.items
        ],
    )
