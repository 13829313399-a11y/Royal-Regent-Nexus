from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from hashlib import sha256
from math import floor
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.time import business_now
from app.models.ai_guard import AIGuardDailyBudget
from app.models.ai_observability import AIMetricEvent
from app.models.ai_task import AITask
from app.models.auth import AuthUser, SystemNotification

alert_logger = logging.getLogger("app.ai.observability.alerts")

AlertType = Literal[
    "COST_PER_SUCCESSFUL_TASK",
    "PROVIDER_FAILURE",
    "TOOL_FAILURE",
    "WORKER_RECOVERY",
    "SCANNER_STALE",
    "BUDGET",
]

_TARGET_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
_ALERT_TITLES: dict[AlertType, str] = {
    "COST_PER_SUCCESSFUL_TASK": "AI 成功任务成本告警",
    "PROVIDER_FAILURE": "AI Provider 故障告警",
    "TOOL_FAILURE": "AI Tool 故障告警",
    "WORKER_RECOVERY": "AI Worker 恢复告警",
    "SCANNER_STALE": "AI 文件扫描签名告警",
    "BUDGET": "AI 日预算告警",
}


class AIAlertConfigurationError(RuntimeError):
    pass


class AIAlertEvidenceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AIOperationalAlertItem:
    alert_type: AlertType
    triggered: bool
    observed_value: int
    threshold_value: int
    notification_ids: tuple[str, ...] = ()
    detail_code: str = ""


@dataclass(frozen=True, slots=True)
class AIOperationalAlertEvaluation:
    evaluated_at: str
    window_minutes: int
    recipient_count: int
    items: tuple[AIOperationalAlertItem, ...]


@dataclass(frozen=True, slots=True)
class AIOperationalAlertAcknowledgementItem:
    notification_id: str
    alert_type: AlertType
    status: Literal["unread", "read", "handled"]
    created_at: str
    read_at: str
    handled_at: str
    acknowledged: bool


@dataclass(frozen=True, slots=True)
class AIOperationalAlertAcknowledgementReport:
    generated_at: str
    notification_count: int
    recipient_count: int
    complete_delivery_set: bool
    all_acknowledged: bool
    items: tuple[AIOperationalAlertAcknowledgementItem, ...]


def alert_target_user_ids(settings: Settings) -> tuple[str, ...]:
    values = tuple(
        item.strip()
        for item in settings.ai_alert_target_user_ids.split(",")
        if item.strip()
    )
    if not values:
        raise AIAlertConfigurationError("alert_target_users_missing")
    if len(values) > 16 or len(set(values)) != len(values):
        raise AIAlertConfigurationError("alert_target_users_invalid")
    if any(_TARGET_ID_PATTERN.fullmatch(item) is None for item in values):
        raise AIAlertConfigurationError("alert_target_users_invalid")
    return values


def ensure_ai_alert_runtime_ready(settings: Settings) -> None:
    if not settings.ai_operational_alerts_enabled:
        return
    missing: list[str] = []
    try:
        alert_target_user_ids(settings)
    except AIAlertConfigurationError:
        missing.append("target_users")
    if not settings.ai_observability_enabled:
        missing.append("observability")
    if not settings.ai_metric_export_enabled:
        missing.append("metric_export")
    if (
        settings.ai_input_token_cost_usd_per_million <= 0
        or settings.ai_output_token_cost_usd_per_million <= 0
    ):
        missing.append("approved_token_rates")
    thresholds = {
        "cost_threshold": settings.ai_cost_per_successful_task_alert_microusd,
        "provider_failure_threshold": settings.ai_provider_failure_alert_count,
        "tool_failure_threshold": settings.ai_tool_failure_alert_count,
        "worker_recovery_threshold": settings.ai_worker_recovery_alert_count,
        "budget_threshold": settings.ai_budget_alert_percent,
        "scanner_age_threshold": settings.ai_scanner_signature_max_age_hours,
    }
    missing.extend(name for name, value in thresholds.items() if value <= 0)
    if not settings.ai_artifacts_enabled:
        missing.append("artifacts")
    if settings.ai_artifact_scanner_backend != "clamav":
        missing.append("clamav_scanner")
    if missing:
        raise AIAlertConfigurationError(
            "AI operational alert readiness incomplete: " + ", ".join(missing)
        )


def ensure_ai_alert_targets(db: Session, settings: Settings) -> tuple[str, ...]:
    if not settings.ai_operational_alerts_enabled:
        return ()
    target_ids = alert_target_user_ids(settings)
    active_ids = set(
        db.scalars(
            select(AuthUser.id).where(
                AuthUser.id.in_(target_ids),
                AuthUser.status == "active",
            )
        ).all()
    )
    if active_ids != set(target_ids):
        raise AIAlertConfigurationError("alert_target_users_not_active")
    return target_ids


def probe_clamav_signature_age_hours(
    settings: Settings,
    *,
    now: datetime | None = None,
) -> float:
    with socket.create_connection(
        (settings.ai_artifact_clamav_host, settings.ai_artifact_clamav_port),
        timeout=settings.ai_artifact_clamav_timeout_seconds,
    ) as connection:
        connection.settimeout(settings.ai_artifact_clamav_timeout_seconds)
        connection.sendall(b"zVERSION\0")
        chunks: list[bytes] = []
        size = 0
        while size < 1024:
            chunk = connection.recv(min(256, 1024 - size))
            if not chunk:
                break
            chunks.append(chunk)
            size += len(chunk)
            if b"\0" in chunk or b"\n" in chunk:
                break
    response = b"".join(chunks).split(b"\0", 1)[0].decode("ascii", errors="strict")
    parts = response.strip().split("/", 2)
    if len(parts) != 3 or not parts[1].isdigit():
        raise ValueError("clamav_version_response_invalid")
    signature_time = parsedate_to_datetime(parts[2].strip())
    if signature_time is None:
        raise ValueError("clamav_signature_time_missing")
    if signature_time.tzinfo is None:
        signature_time = signature_time.replace(tzinfo=timezone.utc)
    current = now or datetime.now(timezone.utc)
    return max(
        0.0,
        (
            current.astimezone(timezone.utc) - signature_time.astimezone(timezone.utc)
        ).total_seconds()
        / 3600,
    )


def _count_events(
    db: Session,
    *,
    event_type: str,
    cutoff: str,
) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AIMetricEvent)
            .where(
                AIMetricEvent.event_type == event_type,
                AIMetricEvent.status == "FAILURE",
                AIMetricEvent.created_at >= cutoff,
            )
        )
        or 0
    )


def _cost_per_successful_task(db: Session, *, cutoff: str) -> int:
    rows = db.execute(
        select(
            AIMetricEvent.task_id,
            func.sum(AIMetricEvent.estimated_cost_microusd),
        )
        .join(AITask, AITask.id == AIMetricEvent.task_id)
        .where(
            AITask.state == "COMPLETED",
            AITask.updated_at >= cutoff,
            AIMetricEvent.event_type == "MODEL_RUN",
            AIMetricEvent.cost_basis != "UNAVAILABLE",
        )
        .group_by(AIMetricEvent.task_id)
    ).all()
    if not rows:
        return 0
    return sum(int(row[1] or 0) for row in rows) // len(rows)


def _worker_recovery_count(db: Session, *, cutoff: str) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(AITask)
            .where(AITask.claim_count > 1, AITask.updated_at >= cutoff)
        )
        or 0
    )


def _budget_percent(db: Session, settings: Settings, *, budget_day: str) -> int:
    largest = db.scalar(
        select(
            func.max(
                AIGuardDailyBudget.used_tokens + AIGuardDailyBudget.reserved_tokens
            )
        ).where(AIGuardDailyBudget.budget_day == budget_day)
    )
    if largest is None or settings.ai_pilot_daily_token_budget <= 0:
        return 0
    return (100 * int(largest)) // settings.ai_pilot_daily_token_budget


def _message(item: AIOperationalAlertItem, window_minutes: int) -> str:
    label = {
        "COST_PER_SUCCESSFUL_TASK": "成功任务平均估算成本（微美元）",
        "PROVIDER_FAILURE": "Provider 失败次数",
        "TOOL_FAILURE": "Tool 失败次数",
        "WORKER_RECOVERY": "发生恢复的 Worker 任务数",
        "SCANNER_STALE": "ClamAV 签名年龄（小时）",
        "BUDGET": "单用户日预算最高使用率（百分比）",
    }[item.alert_type]
    suffix = f"，状态 {item.detail_code}" if item.detail_code else ""
    return (
        f"过去 {window_minutes} 分钟{label}为 {item.observed_value}，"
        f"已达到阈值 {item.threshold_value}{suffix}。请核对现场证据并处理通知。"
    )


def _notification_id(
    *,
    alert_type: AlertType,
    target_user_id: str,
    bucket: int,
) -> str:
    digest = sha256(f"{alert_type}|{target_user_id}|{bucket}".encode()).hexdigest()[:40]
    return f"ainotif-{digest}"


def _create_notifications(
    db: Session,
    *,
    item: AIOperationalAlertItem,
    target_ids: tuple[str, ...],
    settings: Settings,
    now: datetime,
) -> tuple[str, ...]:
    bucket_seconds = settings.ai_alert_cooldown_minutes * 60
    bucket = int(now.timestamp()) // bucket_seconds
    created_at = now.isoformat(timespec="seconds")
    notification_ids: list[str] = []
    for target_id in target_ids:
        notification_id = _notification_id(
            alert_type=item.alert_type,
            target_user_id=target_id,
            bucket=bucket,
        )
        notification_ids.append(notification_id)
        if db.get(SystemNotification, notification_id) is not None:
            continue
        payload = {
            "schema_version": "ai-operational-alert-v1",
            "alert_type": item.alert_type,
            "observed_value": item.observed_value,
            "threshold_value": item.threshold_value,
            "window_minutes": settings.ai_alert_window_minutes,
            "detail_code": item.detail_code,
            "metadata_only": True,
        }
        try:
            with db.begin_nested():
                db.add(
                    SystemNotification(
                        id=notification_id,
                        target_user_id=target_id,
                        target_permission="",
                        target_factory_id="",
                        target_department="",
                        type="ai_operational_alert",
                        title=_ALERT_TITLES[item.alert_type],
                        message=_message(item, settings.ai_alert_window_minutes),
                        payload_json=json.dumps(
                            payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                        status="unread",
                        created_at=created_at,
                        read_at="",
                        handled_at="",
                    )
                )
                db.flush()
        except IntegrityError:
            # Concurrent API instances use the same deterministic ID. The
            # unique primary key turns a race into an idempotent replay.
            pass
    return tuple(notification_ids)


def evaluate_ai_operational_alerts(
    db: Session,
    *,
    settings: Settings,
    now: datetime | None = None,
    scanner_age_probe: Callable[[Settings], float] | None = None,
) -> AIOperationalAlertEvaluation:
    ensure_ai_alert_runtime_ready(settings)
    if not settings.ai_operational_alerts_enabled:
        raise AIAlertConfigurationError("operational_alerts_disabled")
    target_ids = ensure_ai_alert_targets(db, settings)
    current = now or business_now()
    cutoff = (current - timedelta(minutes=settings.ai_alert_window_minutes)).isoformat(
        timespec="seconds"
    )
    scanner_detail = ""
    try:
        scanner_age = (
            scanner_age_probe(settings)
            if scanner_age_probe is not None
            else probe_clamav_signature_age_hours(settings, now=current)
        )
        scanner_observed = floor(max(scanner_age, 0))
    except (OSError, ValueError, UnicodeError):
        scanner_observed = settings.ai_scanner_signature_max_age_hours + 1
        scanner_detail = "SCANNER_PROBE_FAILED"

    observations: tuple[tuple[AlertType, int, int, str], ...] = (
        (
            "COST_PER_SUCCESSFUL_TASK",
            _cost_per_successful_task(db, cutoff=cutoff),
            settings.ai_cost_per_successful_task_alert_microusd,
            "",
        ),
        (
            "PROVIDER_FAILURE",
            _count_events(db, event_type="MODEL_RUN", cutoff=cutoff),
            settings.ai_provider_failure_alert_count,
            "",
        ),
        (
            "TOOL_FAILURE",
            _count_events(db, event_type="TOOL_CALL", cutoff=cutoff),
            settings.ai_tool_failure_alert_count,
            "",
        ),
        (
            "WORKER_RECOVERY",
            _worker_recovery_count(db, cutoff=cutoff),
            settings.ai_worker_recovery_alert_count,
            "",
        ),
        (
            "SCANNER_STALE",
            scanner_observed,
            settings.ai_scanner_signature_max_age_hours,
            scanner_detail,
        ),
        (
            "BUDGET",
            _budget_percent(db, settings, budget_day=current.date().isoformat()),
            settings.ai_budget_alert_percent,
            "",
        ),
    )
    results: list[AIOperationalAlertItem] = []
    for alert_type, observed, threshold, detail_code in observations:
        base_item = AIOperationalAlertItem(
            alert_type=alert_type,
            triggered=observed >= threshold,
            observed_value=observed,
            threshold_value=threshold,
            detail_code=detail_code,
        )
        notification_ids = (
            _create_notifications(
                db,
                item=base_item,
                target_ids=target_ids,
                settings=settings,
                now=current,
            )
            if base_item.triggered
            else ()
        )
        results.append(
            AIOperationalAlertItem(
                alert_type=base_item.alert_type,
                triggered=base_item.triggered,
                observed_value=base_item.observed_value,
                threshold_value=base_item.threshold_value,
                notification_ids=notification_ids,
                detail_code=base_item.detail_code,
            )
        )
    db.commit()
    return AIOperationalAlertEvaluation(
        evaluated_at=current.isoformat(timespec="seconds"),
        window_minutes=settings.ai_alert_window_minutes,
        recipient_count=len(target_ids),
        items=tuple(results),
    )


def build_ai_operational_alert_acknowledgement_report(
    db: Session,
    *,
    notification_ids: tuple[str, ...],
    now: datetime | None = None,
) -> AIOperationalAlertAcknowledgementReport:
    if not notification_ids or len(notification_ids) > 96:
        raise AIAlertEvidenceError("alert_notification_ids_invalid")
    if len(notification_ids) != len(set(notification_ids)):
        raise AIAlertEvidenceError("alert_notification_ids_invalid")

    records = list(
        db.scalars(
            select(SystemNotification).where(
                SystemNotification.id.in_(notification_ids),
                SystemNotification.type == "ai_operational_alert",
            )
        ).all()
    )
    records_by_id = {record.id: record for record in records}
    if set(records_by_id) != set(notification_ids):
        raise AIAlertEvidenceError("alert_notifications_not_found")

    target_ids: set[str] = set()
    target_ids_by_alert_type: dict[AlertType, set[str]] = {}
    created_at_values: set[str] = set()
    items: list[AIOperationalAlertAcknowledgementItem] = []
    for notification_id in notification_ids:
        record = records_by_id[notification_id]
        try:
            payload = json.loads(record.payload_json)
        except (json.JSONDecodeError, TypeError) as exc:
            raise AIAlertEvidenceError("alert_notification_payload_invalid") from exc
        alert_type = payload.get("alert_type") if isinstance(payload, dict) else None
        if (
            not isinstance(payload, dict)
            or payload.get("schema_version") != "ai-operational-alert-v1"
            or payload.get("metadata_only") is not True
            or alert_type not in _ALERT_TITLES
            or record.status not in {"unread", "read", "handled"}
            or not record.target_user_id
            or (record.status == "handled" and not record.handled_at)
            or (record.status != "handled" and bool(record.handled_at))
        ):
            raise AIAlertEvidenceError("alert_notification_integrity_invalid")
        acknowledged = record.status == "handled" and bool(record.handled_at)
        target_ids.add(record.target_user_id)
        target_ids_by_alert_type.setdefault(alert_type, set()).add(
            record.target_user_id
        )
        created_at_values.add(record.created_at)
        items.append(
            AIOperationalAlertAcknowledgementItem(
                notification_id=record.id,
                alert_type=alert_type,
                status=record.status,
                created_at=record.created_at,
                read_at=record.read_at,
                handled_at=record.handled_at,
                acknowledged=acknowledged,
            )
        )

    current = now or business_now()
    complete_delivery_set = (
        set(target_ids_by_alert_type) == set(_ALERT_TITLES)
        and all(recipients == target_ids for recipients in target_ids_by_alert_type.values())
        and len(items) == len(_ALERT_TITLES) * len(target_ids)
        and len(created_at_values) == 1
    )
    return AIOperationalAlertAcknowledgementReport(
        generated_at=current.isoformat(timespec="seconds"),
        notification_count=len(items),
        recipient_count=len(target_ids),
        complete_delivery_set=complete_delivery_set,
        all_acknowledged=(
            complete_delivery_set and all(item.acknowledged for item in items)
        ),
        items=tuple(items),
    )


async def ai_operational_alert_loop(
    session_factory: sessionmaker[Session],
    *,
    settings: Settings,
) -> None:
    while True:
        if settings.ai_operational_alerts_enabled:
            try:
                await asyncio.to_thread(
                    _evaluate_alerts_with_session,
                    session_factory,
                    settings,
                )
            except Exception:
                alert_logger.exception("ai_operational_alert_evaluation_failed")
        await asyncio.sleep(settings.ai_alert_evaluation_interval_seconds)


def _evaluate_alerts_with_session(
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    with session_factory() as db:
        evaluate_ai_operational_alerts(db, settings=settings)
