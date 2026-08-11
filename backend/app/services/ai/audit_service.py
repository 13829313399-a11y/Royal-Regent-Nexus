from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

from app.schemas.ai import AIToolAuditPolicy
from app.services.ai.tool_registry import ToolSpec
from app.services.auth import add_auth_audit

tool_logger = logging.getLogger("app.ai.tool")


@dataclass(frozen=True, slots=True)
class ToolAuditTimer:
    started_at: float

    @classmethod
    def start(cls) -> ToolAuditTimer:
        return cls(started_at=perf_counter())

    @property
    def duration_ms(self) -> float:
        return (perf_counter() - self.started_at) * 1000


def log_tool_outcome(
    *,
    spec: ToolSpec | None,
    request_id: str,
    user_id: str,
    status: str,
    timer: ToolAuditTimer,
    row_count: int = 0,
    field_count: int = 0,
    byte_count: int = 0,
    error_code: str = "",
) -> None:
    if spec is not None and spec.audit_policy == AIToolAuditPolicy.NONE:
        return
    tool_name = spec.name if spec is not None else "unregistered"
    tool_logger.info(
        "ai_tool request_id=%s user_id=%s tool=%s status=%s "
        "duration_ms=%.2f rows=%d fields=%d bytes=%d error_code=%s",
        request_id,
        user_id,
        tool_name,
        status,
        timer.duration_ms,
        row_count,
        field_count,
        byte_count,
        error_code,
    )


def record_security_denial(
    *,
    spec: ToolSpec,
    context: object,
    factory_id: str,
    reason_code: str,
) -> None:
    if spec.audit_policy not in {
        AIToolAuditPolicy.METADATA_ONLY,
        AIToolAuditPolicy.SECURITY_DENIALS,
    }:
        return
    session_factory = getattr(context, "session_factory", None)
    if session_factory is None:
        # A borrowed tool/business Session must never be committed or rolled back by
        # an audit side effect. The denial itself is still logged by log_tool_outcome.
        return
    try:
        db = session_factory()
    except Exception:  # noqa: BLE001 - audit failure must not mask denial
        return
    user = getattr(context, "user", None)
    if user is None:
        try:
            db.close()
        except Exception:  # noqa: BLE001, S110 - denial still stands
            pass
        return
    try:
        add_auth_audit(
            db,
            "ai_tool_permission_denied",
            username=user.username,
            user_id=user.id,
            detail=(
                f"tool={spec.name};factory={factory_id};reason={reason_code}"
            ),
        )
        db.commit()
    except Exception:  # noqa: BLE001 - audit failure must not grant or mask denial
        try:
            db.rollback()
        except Exception:  # noqa: BLE001, S110 - denial still stands
            pass
    finally:
        try:
            db.close()
        except Exception:  # noqa: BLE001, S110 - denial still stands
            pass
