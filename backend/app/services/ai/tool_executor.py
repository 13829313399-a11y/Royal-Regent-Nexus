from __future__ import annotations

import asyncio
import inspect
import json
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace

from pydantic import BaseModel, ValidationError
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.inspection import inspect as sqlalchemy_inspect
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.schemas.ai import (
    AIServerPageContext,
    AIToolError,
    AIToolErrorCode,
    AIToolResultEnvelope,
    AIToolResultMetadata,
    AIToolRiskLevel,
)
from app.services.ai.audit_service import (
    ToolAuditTimer,
    log_tool_outcome,
    record_security_denial,
)
from app.services.ai.evidence import EvidenceError, build_tool_evidence
from app.services.ai.providers import ProviderToolCall
from app.services.ai.tool_registry import ToolRegistry, ToolSpec
from app.services.auth import (
    ALLOWED_FACTORY_IDS,
    AuthContext,
    authorization_decision,
)

_MAX_ARGUMENT_BYTES = 16_384
_MAX_RESULT_DEPTH = 16


class InvalidToolResult(TypeError):
    pass


@dataclass(frozen=True, slots=True)
class ToolExecutionContext:
    db: Session | None
    user: AuthContext
    request_id: str
    page_context: object | None = None
    tool_groups: tuple[str, ...] = ()
    session_factory: Callable[[], Session] | None = None
    tool_call_id: str = ""


@dataclass(frozen=True, slots=True)
class ToolExecutionOutcome:
    call_id: str
    tool_name: str
    display_label: str
    ok: bool
    provider_output_json: str
    safe_event_payload: dict[str, object]
    error_code: str = ""
    row_count: int = 0
    field_count: int = 0
    byte_count: int = 0
    truncated: bool = False


class ToolExecutor:
    def __init__(self, registry: ToolRegistry, settings: Settings) -> None:
        self.registry = registry
        self.settings = settings

    async def execute(
        self,
        call: ProviderToolCall,
        context: ToolExecutionContext,
    ) -> ToolExecutionOutcome:
        timer = ToolAuditTimer.start()
        spec = self.registry.resolve(call.name)
        if spec is None:
            return self._failure(
                call=call,
                spec=None,
                context=context,
                timer=timer,
                code=AIToolErrorCode.UNKNOWN_TOOL,
                message="请求的工具不可用。",
            )
        if spec.risk_level not in {
            AIToolRiskLevel.READ_ONLY,
            AIToolRiskLevel.PREVIEW_WITH_AUDIT,
        }:
            return self._failure(
                call=call,
                spec=spec,
                context=context,
                timer=timer,
                code=AIToolErrorCode.RISK_NOT_ALLOWED,
                message="当前阶段不允许执行正式业务写工具。",
            )
        if not self.registry.is_in_request_scope(spec, context):
            return self._failure(
                call=call,
                spec=None,
                context=context,
                timer=timer,
                code=AIToolErrorCode.UNKNOWN_TOOL,
                message="请求的工具不可用。",
            )

        try:
            if len(call.arguments_json.encode("utf-8")) > _MAX_ARGUMENT_BYTES:
                raise ValueError("arguments too large")
            arguments = spec.input_model.model_validate_json(call.arguments_json)
        except (UnicodeEncodeError, ValidationError, ValueError):
            return self._failure(
                call=call,
                spec=spec,
                context=context,
                timer=timer,
                code=AIToolErrorCode.INVALID_ARGUMENTS,
                message="工具参数格式不正确。",
            )

        factory_id = self._resolve_factory(spec, arguments, context)
        if spec.factory_argument is not None and factory_id is None:
            return self._failure(
                call=call,
                spec=spec,
                context=context,
                timer=timer,
                code=AIToolErrorCode.INVALID_FACTORY,
                message="工具厂区参数无效。",
            )

        if spec.required_permission is not None:
            assert factory_id is not None
            decisions = tuple(
                authorization_decision(
                    context.user,
                    spec.required_permission,
                    factory_id,
                    department,
                )
                for department in spec.allowed_departments
            )
            if not any(decision[0] for decision in decisions):
                reason_code = next(
                    (
                        decision[1]
                        for decision in decisions
                        if decision[1] != "default"
                    ),
                    "default",
                )
                await _record_security_denial(
                    spec=spec,
                    context=context,
                    factory_id=factory_id,
                    reason_code=reason_code,
                )
                return self._failure(
                    call=call,
                    spec=spec,
                    context=context,
                    timer=timer,
                    code=AIToolErrorCode.PERMISSION_DENIED,
                    message="没有执行该工具所需的厂区或部门权限。",
                )

        execution_context = replace(
            context,
            tool_call_id=call.call_id,
            tool_groups=self.registry.available_tool_groups(context),
        )
        try:
            async with asyncio.timeout(spec.timeout_seconds):
                serialized = await _execute_and_serialize(
                    spec,
                    execution_context,
                    arguments,
                )
            safe_data = _normalize_result(serialized)
        except TimeoutError:
            return self._failure(
                call=call,
                spec=spec,
                context=context,
                timer=timer,
                code=AIToolErrorCode.TIMEOUT,
                message="工具执行超时。",
                retryable=True,
            )
        except (InvalidToolResult, TypeError, ValueError):
            return self._failure(
                call=call,
                spec=spec,
                context=context,
                timer=timer,
                code=AIToolErrorCode.INVALID_RESULT,
                message="工具返回了不安全或无效的结果。",
            )
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - tool internals stay server-side
            return self._failure(
                call=call,
                spec=spec,
                context=context,
                timer=timer,
                code=AIToolErrorCode.EXECUTION_FAILED,
                message="工具执行失败。",
            )

        row_count, field_count = _result_shape(safe_data)
        if row_count > min(spec.max_result_rows, self.settings.ai_max_tool_result_rows):
            return self._failure(
                call=call,
                spec=spec,
                context=context,
                timer=timer,
                code=AIToolErrorCode.RESULT_ROWS_EXCEEDED,
                message="工具结果超过允许的行数。",
                row_count=row_count,
                field_count=field_count,
            )
        if field_count > self.settings.ai_max_tool_result_fields:
            return self._failure(
                call=call,
                spec=spec,
                context=context,
                timer=timer,
                code=AIToolErrorCode.RESULT_FIELDS_EXCEEDED,
                message="工具结果超过允许的字段数。",
                row_count=row_count,
                field_count=field_count,
            )

        truncated = (
            isinstance(safe_data, dict)
            and safe_data.get("truncated") is True
        )
        evidence = None
        if self.settings.ai_nif_runtime_enabled and self.settings.ai_evidence_v1_enabled:
            try:
                evidence = (
                    build_tool_evidence(
                        spec=spec,
                        request_id=context.request_id,
                        call_id=call.call_id,
                        data=safe_data,
                        factory_id=factory_id,
                        truncated=truncated,
                    ),
                )
            except EvidenceError:
                return self._failure(
                    call=call,
                    spec=spec,
                    context=context,
                    timer=timer,
                    code=AIToolErrorCode.INVALID_RESULT,
                    message="工具结果缺少有效的证据元数据。",
                    row_count=row_count,
                    field_count=field_count,
                )

        envelope = AIToolResultEnvelope(
            ok=True,
            tool_name=spec.name,
            data=safe_data,
            metadata=AIToolResultMetadata(
                row_count=row_count,
                field_count=field_count,
                truncated=truncated,
            ),
            evidence=evidence,
        )
        provider_output_json = _dump_json(_envelope_payload(envelope))
        byte_count = len(provider_output_json.encode("utf-8"))
        if byte_count > self.settings.ai_max_tool_result_bytes:
            return self._failure(
                call=call,
                spec=spec,
                context=context,
                timer=timer,
                code=AIToolErrorCode.RESULT_BYTES_EXCEEDED,
                message="工具结果超过允许的字节数。",
                row_count=row_count,
                field_count=field_count,
                byte_count=byte_count,
            )

        event_payload = _event_payload(
            call=call,
            spec=spec,
            envelope=envelope,
            status="completed",
        )
        log_tool_outcome(
            spec=spec,
            request_id=context.request_id,
            user_id=context.user.id,
            status="completed",
            timer=timer,
            row_count=row_count,
            field_count=field_count,
            byte_count=byte_count,
        )
        return ToolExecutionOutcome(
            call_id=call.call_id,
            tool_name=spec.name,
            display_label=spec.display_label,
            ok=True,
            provider_output_json=provider_output_json,
            safe_event_payload=event_payload,
            row_count=row_count,
            field_count=field_count,
            byte_count=byte_count,
            truncated=envelope.metadata.truncated,
        )

    @staticmethod
    def _resolve_factory(
        spec: ToolSpec,
        arguments: BaseModel,
        context: ToolExecutionContext,
    ) -> str | None:
        if spec.factory_argument is None:
            return None
        value = getattr(arguments, spec.factory_argument, None)
        if isinstance(context.page_context, AIServerPageContext):
            page_factory = context.page_context.verified_factory_id
            if page_factory is None:
                return None
            if value in {None, ""}:
                value = page_factory
            elif value != page_factory:
                return None
        if not isinstance(value, str) or value not in ALLOWED_FACTORY_IDS:
            return None
        return value

    def _failure(
        self,
        *,
        call: ProviderToolCall,
        spec: ToolSpec | None,
        context: ToolExecutionContext,
        timer: ToolAuditTimer,
        code: AIToolErrorCode,
        message: str,
        retryable: bool = False,
        row_count: int = 0,
        field_count: int = 0,
        byte_count: int = 0,
    ) -> ToolExecutionOutcome:
        safe_tool_name = spec.name if spec is not None else "unregistered"
        display_label = spec.display_label if spec is not None else "不可用工具"
        envelope = AIToolResultEnvelope(
            ok=False,
            tool_name=safe_tool_name,
            error=AIToolError(
                code=code,
                message=message,
                retryable=retryable,
            ),
        )
        provider_output_json = _dump_json(_envelope_payload(envelope))
        event_payload = _event_payload(
            call=call,
            spec=spec,
            envelope=envelope,
            status="failed",
        )
        log_tool_outcome(
            spec=spec,
            request_id=context.request_id,
            user_id=context.user.id,
            status="failed",
            timer=timer,
            row_count=row_count,
            field_count=field_count,
            byte_count=byte_count,
            error_code=code.value,
        )
        return ToolExecutionOutcome(
            call_id=call.call_id,
            tool_name=safe_tool_name,
            display_label=display_label,
            ok=False,
            provider_output_json=provider_output_json,
            safe_event_payload=event_payload,
            error_code=code.value,
            row_count=row_count,
            field_count=field_count,
            byte_count=byte_count,
        )


async def _invoke(function: object, *args: object) -> object:
    if inspect.iscoroutinefunction(function):
        return await function(*args)
    result = await asyncio.to_thread(function, *args)
    if inspect.isawaitable(result):
        return await result
    return result


async def _execute_and_serialize(
    spec: ToolSpec,
    context: ToolExecutionContext,
    arguments: BaseModel,
) -> object:
    if spec.requires_db and context.session_factory is not None and context.db is None:
        return await asyncio.to_thread(
            _invoke_with_managed_session,
            spec,
            context,
            arguments,
        )
    raw_result = await _invoke(spec.executor, context, arguments)
    return await _invoke(spec.serializer, raw_result)


def _invoke_with_managed_session(
    spec: ToolSpec,
    context: ToolExecutionContext,
    arguments: BaseModel,
) -> object:
    assert context.session_factory is not None
    db = context.session_factory()
    managed_context = replace(context, db=db)
    try:
        _configure_managed_statement_timeout(db, spec)
        raw_result = spec.executor(managed_context, arguments)
        if inspect.isawaitable(raw_result):
            close = getattr(raw_result, "close", None)
            if callable(close):
                close()
            raise TypeError("managed-session tools must be synchronous")
        serialized = spec.serializer(raw_result)
        if inspect.isawaitable(serialized):
            close = getattr(serialized, "close", None)
            if callable(close):
                close()
            raise TypeError("managed-session serializers must be synchronous")
        return serialized
    except DBAPIError as exc:
        if _database_sqlstate(exc) == "57014":
            raise TimeoutError from None
        raise
    finally:
        try:
            db.rollback()
        finally:
            db.close()


def _configure_managed_statement_timeout(db: Session, spec: ToolSpec) -> None:
    get_bind = getattr(db, "get_bind", None)
    if not callable(get_bind):
        return
    bind = get_bind()
    dialect_name = getattr(getattr(bind, "dialect", None), "name", "")
    if dialect_name != "postgresql":
        return

    outer_timeout_ms = spec.timeout_seconds * 1_000
    margin_ms = max(1, min(250, int(outer_timeout_ms * 0.1)))
    statement_timeout_ms = math.floor(outer_timeout_ms - margin_ms)
    if statement_timeout_ms < 1 or statement_timeout_ms >= outer_timeout_ms:
        raise ValueError("PostgreSQL tool timeout must exceed one millisecond")
    db.execute(
        text("SELECT set_config('statement_timeout', :timeout_value, true)"),
        {"timeout_value": f"{statement_timeout_ms}ms"},
    )


def _database_sqlstate(exc: DBAPIError) -> str:
    original = getattr(exc, "orig", None)
    for source in (original, exc):
        for attribute in ("sqlstate", "pgcode"):
            value = getattr(source, attribute, None)
            if isinstance(value, str):
                return value
    return ""


async def _record_security_denial(
    *,
    spec: ToolSpec,
    context: ToolExecutionContext,
    factory_id: str,
    reason_code: str,
) -> None:
    if context.db is None and context.session_factory is not None:
        await asyncio.to_thread(
            record_security_denial,
            spec=spec,
            context=context,
            factory_id=factory_id,
            reason_code=reason_code,
        )
        return
    record_security_denial(
        spec=spec,
        context=context,
        factory_id=factory_id,
        reason_code=reason_code,
    )


def _normalize_result(value: object) -> object:
    return _normalize_result_value(value, depth=0, seen=set())


def _normalize_result_value(
    value: object,
    *,
    depth: int,
    seen: set[int],
) -> object:
    if depth > _MAX_RESULT_DEPTH:
        raise InvalidToolResult("tool result is too deeply nested")
    if _is_orm_value(value):
        raise InvalidToolResult("ORM values require a dedicated serializer")
    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json")
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidToolResult("non-finite numbers are not allowed")
        return value

    if isinstance(value, Mapping):
        identity = id(value)
        if identity in seen:
            raise InvalidToolResult("cyclic tool result")
        seen.add(identity)
        try:
            result: dict[str, object] = {}
            for key, item in value.items():
                if not isinstance(key, str):
                    raise InvalidToolResult("tool result keys must be strings")
                result[key] = _normalize_result_value(
                    item,
                    depth=depth + 1,
                    seen=seen,
                )
            return result
        finally:
            seen.remove(identity)

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        identity = id(value)
        if identity in seen:
            raise InvalidToolResult("cyclic tool result")
        seen.add(identity)
        try:
            return [
                _normalize_result_value(item, depth=depth + 1, seen=seen)
                for item in value
            ]
        finally:
            seen.remove(identity)

    raise InvalidToolResult(f"unsupported result value: {type(value).__name__}")


def _is_orm_value(value: object) -> bool:
    try:
        inspected = sqlalchemy_inspect(value, raiseerr=False)
    except Exception:  # noqa: BLE001 - inspection itself must fail closed
        return True
    return inspected is not None


def _result_shape(value: object) -> tuple[int, int]:
    max_rows = 0
    max_field_width = 0

    def visit(item: object) -> None:
        nonlocal max_rows, max_field_width
        if isinstance(item, dict):
            max_field_width = max(max_field_width, len(item))
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            max_rows = max(max_rows, len(item))
            for nested in item:
                visit(nested)

    visit(value)
    return max_rows, max_field_width


def _event_payload(
    *,
    call: ProviderToolCall,
    spec: ToolSpec | None,
    envelope: AIToolResultEnvelope,
    status: str,
) -> dict[str, object]:
    return {
        "tool_call_id": call.call_id,
        "tool_name": spec.name if spec is not None else "unregistered",
        "display_label": spec.display_label if spec is not None else "不可用工具",
        "status": status,
        "result": _envelope_payload(envelope),
    }


def _envelope_payload(envelope: AIToolResultEnvelope) -> dict[str, object]:
    payload = envelope.model_dump(mode="json")
    if payload.get("evidence") is None:
        payload.pop("evidence", None)
    return payload


def _dump_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
