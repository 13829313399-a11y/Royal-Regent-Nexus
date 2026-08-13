from __future__ import annotations

from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.time import business_now, parse_business_timestamp
from app.db import get_db
from app.schemas.ai.feedback import (
    AIEvalRunData,
    AIFeedbackCreate,
    AIFeedbackData,
    AIFeedbackPage,
    AIFeedbackReview,
    AIMetricEventData,
    AIMetricSummary,
    AIOperationalAlertAcknowledgementItemData,
    AIOperationalAlertAcknowledgementReportData,
    AIOperationalAlertAcknowledgementRequest,
    AIOperationalAlertEvaluationData,
    AIOperationalAlertItemData,
)
from app.services.ai.feedback import (
    FeedbackError,
    create_feedback,
    feedback_data,
    list_feedback,
    review_feedback,
)
from app.services.ai.observability.alerts import (
    AIAlertConfigurationError,
    AIAlertEvidenceError,
    build_ai_operational_alert_acknowledgement_report,
    evaluate_ai_operational_alerts,
)
from app.services.ai.observability.metrics import (
    build_metric_summary,
    list_eval_runs,
    list_metric_events,
)
from app.services.auth import AuthContext, get_current_user
from app.services.business_authz import is_wildcard_super_admin

router = APIRouter(prefix="/api/ai", tags=["ai-feedback"])
DbSession = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[AuthContext, Depends(get_current_user)]


def _feedback_error(exc: FeedbackError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"code": exc.code, "message": exc.public_message, "retryable": False},
    )


def _require_feedback() -> None:
    if not settings.ai_feedback_enabled:
        raise HTTPException(status_code=404, detail="Not Found")


def _require_admin_export(user: AuthContext) -> None:
    if not settings.ai_metric_export_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    if not is_wildcard_super_admin(user):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "AI_METRIC_ADMIN_REQUIRED",
                "message": "只有集团系统管理员可以读取 AI 评测与指标。",
                "retryable": False,
            },
        )


def _require_operational_alerts(user: AuthContext) -> None:
    if not settings.ai_operational_alerts_enabled:
        raise HTTPException(status_code=404, detail="Not Found")
    _require_admin_export(user)


def _metric_range(from_time: str, to_time: str) -> tuple[str, str]:
    now = business_now()
    start = (
        parse_business_timestamp(from_time) if from_time else now - timedelta(days=7)
    )
    end = parse_business_timestamp(to_time) if to_time else now
    if start is None or end is None or end < start:
        raise HTTPException(status_code=422, detail="指标时间范围无效")
    if end - start > timedelta(days=93):
        raise HTTPException(status_code=422, detail="指标时间范围最多 93 天")
    return start.isoformat(timespec="seconds"), end.isoformat(timespec="seconds")


@router.post("/feedback", response_model=AIFeedbackData)
def post_feedback(
    payload: AIFeedbackCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_feedback()
    try:
        return feedback_data(create_feedback(db, payload=payload, user=current_user))
    except FeedbackError as exc:
        raise _feedback_error(exc) from exc


@router.get("/feedback/mine", response_model=AIFeedbackPage)
def get_my_feedback(
    db: DbSession,
    current_user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    _require_feedback()
    return list_feedback(
        db,
        owner_user_id=current_user.id,
        status="",
        limit=limit,
        offset=offset,
    )


@router.get("/admin/feedback", response_model=AIFeedbackPage)
def get_admin_feedback(
    db: DbSession,
    current_user: CurrentUser,
    status: Annotated[str, Query(max_length=24)] = "",
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    _require_admin_export(current_user)
    if status and status not in {
        "SUBMITTED",
        "TRIAGED",
        "EVAL_CANDIDATE",
        "DISMISSED",
    }:
        raise HTTPException(status_code=422, detail="反馈状态无效")
    return list_feedback(
        db,
        owner_user_id=None,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.patch("/admin/feedback/{feedback_id}", response_model=AIFeedbackData)
def patch_admin_feedback(
    feedback_id: str,
    payload: AIFeedbackReview,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_admin_export(current_user)
    try:
        record = review_feedback(
            db,
            feedback_id=feedback_id,
            payload=payload,
            reviewer=current_user,
        )
    except FeedbackError as exc:
        raise _feedback_error(exc) from exc
    return feedback_data(record)


@router.get("/admin/metrics/summary", response_model=AIMetricSummary)
def get_metric_summary(
    db: DbSession,
    current_user: CurrentUser,
    from_time: Annotated[str, Query(max_length=40)] = "",
    to_time: Annotated[str, Query(max_length=40)] = "",
):
    _require_admin_export(current_user)
    start, end = _metric_range(from_time, to_time)
    return build_metric_summary(db, from_time=start, to_time=end)


@router.get("/admin/metrics/events", response_model=list[AIMetricEventData])
def get_metric_events(
    db: DbSession,
    current_user: CurrentUser,
    from_time: Annotated[str, Query(max_length=40)] = "",
    to_time: Annotated[str, Query(max_length=40)] = "",
    limit: Annotated[int, Query(ge=1, le=5000)] = 1000,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    _require_admin_export(current_user)
    start, end = _metric_range(from_time, to_time)
    return list_metric_events(
        db,
        from_time=start,
        to_time=end,
        limit=limit,
        offset=offset,
    )


@router.get("/admin/evals/runs", response_model=list[AIEvalRunData])
def get_eval_runs(
    db: DbSession,
    current_user: CurrentUser,
    from_time: Annotated[str, Query(max_length=40)] = "",
    to_time: Annotated[str, Query(max_length=40)] = "",
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    _require_admin_export(current_user)
    start, end = _metric_range(from_time, to_time)
    return list_eval_runs(
        db,
        from_time=start,
        to_time=end,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/admin/alerts/evaluate",
    response_model=AIOperationalAlertEvaluationData,
)
def post_operational_alert_evaluation(
    db: DbSession,
    current_user: CurrentUser,
):
    _require_operational_alerts(current_user)
    try:
        evaluation = evaluate_ai_operational_alerts(db, settings=settings)
    except AIAlertConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "AI_ALERT_CHANNEL_UNAVAILABLE",
                "message": "AI 运维告警通道尚未完成配置。",
                "retryable": False,
            },
        ) from exc
    return AIOperationalAlertEvaluationData(
        evaluated_at=evaluation.evaluated_at,
        window_minutes=evaluation.window_minutes,
        recipient_count=evaluation.recipient_count,
        items=[
            AIOperationalAlertItemData(
                alert_type=item.alert_type,
                triggered=item.triggered,
                observed_value=item.observed_value,
                threshold_value=item.threshold_value,
                notification_ids=list(item.notification_ids),
                detail_code=item.detail_code,
            )
            for item in evaluation.items
        ],
    )


@router.post(
    "/admin/alerts/acknowledgements",
    response_model=AIOperationalAlertAcknowledgementReportData,
)
def post_operational_alert_acknowledgements(
    payload: AIOperationalAlertAcknowledgementRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    _require_operational_alerts(current_user)
    try:
        report = build_ai_operational_alert_acknowledgement_report(
            db,
            notification_ids=tuple(payload.notification_ids),
        )
    except AIAlertEvidenceError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "AI_ALERT_ACKNOWLEDGEMENT_EVIDENCE_INVALID",
                "message": "指定的 AI 运维告警确认记录不完整或无法验证。",
                "retryable": False,
            },
        ) from exc
    return AIOperationalAlertAcknowledgementReportData(
        generated_at=report.generated_at,
        notification_count=report.notification_count,
        recipient_count=report.recipient_count,
        complete_delivery_set=report.complete_delivery_set,
        all_acknowledged=report.all_acknowledged,
        items=[
            AIOperationalAlertAcknowledgementItemData(
                notification_id=item.notification_id,
                alert_type=item.alert_type,
                status=item.status,
                created_at=item.created_at,
                read_at=item.read_at,
                handled_at=item.handled_at,
                acknowledged=item.acknowledged,
            )
            for item in report.items
        ],
    )
