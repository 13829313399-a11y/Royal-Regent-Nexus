from __future__ import annotations

import base64
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from uuid import uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.time import business_now, parse_business_timestamp
from app.models.ai_conversation import (
    AIConversation,
    AIConversationSummary,
    AIMessage,
)
from app.models.ai_conversation import (
    AIConversationContextBinding as AIConversationContextBindingRecord,
)
from app.schemas.ai.context import AIPageContextInput, AISelectedEntityInput
from app.schemas.ai.conversation import (
    AIConversationContextBinding,
    AIConversationContextUpdate,
    AIConversationCreate,
    AIConversationDetail,
    AIConversationListItem,
    AIConversationListPage,
    AIConversationMessageCreate,
    AIConversationMessageData,
    AIConversationSummaryData,
    AIConversationUpdate,
)
from app.schemas.ai.evidence import AIEvidenceReferenceV1
from app.services.ai.context_builder import (
    AIPageContextValidationError,
    build_server_page_context,
)
from app.services.ai.providers.base import ProviderMessage
from app.services.auth import ALLOWED_FACTORY_IDS, AuthContext, authorization_decision

MAX_TITLE_CHARS = 160
MAX_MESSAGE_CHARS = 8_000
MAX_SUMMARY_CHARS = 4_000
MAX_LIST_PAGE = 50
MAX_DETAIL_MESSAGES = 50
MAX_HISTORY_MESSAGES = 12
MAX_HISTORY_CHARS = 40_000

_OPAQUE_ID = re.compile(r"(?:aicv|aimsg|aisum)-[0-9a-f]{32}")
_IDEMPOTENCY_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,127}")
_SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(
        r"(?i)\b(?:api[_ -]?key|access[_ -]?token|password|密码|密钥)"
        r"\s*[:=：]\s*['\"]?[^\s'\"]{6,}"
    ),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{12,}"),
)


class ConversationError(RuntimeError):
    code = "AI_CONVERSATION_ERROR"
    status_code = 400

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.public_message = message


class ConversationNotFoundError(ConversationError):
    code = "AI_CONVERSATION_NOT_FOUND"
    status_code = 404


class ConversationConflictError(ConversationError):
    code = "AI_CONVERSATION_CONFLICT"
    status_code = 409


class ConversationStaleError(ConversationError):
    code = "AI_CONVERSATION_STALE"
    status_code = 412


class ConversationValidationError(ConversationError):
    code = "AI_CONVERSATION_INVALID"
    status_code = 422


@dataclass(frozen=True, slots=True)
class AssistantMessageMetadata:
    skill_id: str = ""
    skill_version: str = ""
    skill_hash: str = ""
    prompt_version: str = ""
    prompt_hash: str = ""
    provider_profile: str = ""
    provider_model_alias: str = ""
    usage: dict[str, int] | None = None
    evidence: tuple[AIEvidenceReferenceV1, ...] = ()
    required_access: tuple[tuple[str, tuple[str, ...]], ...] = ()


@dataclass(frozen=True, slots=True)
class ConversationHistory:
    conversation_id: str
    messages: tuple[ProviderMessage, ...]
    message_count: int
    input_chars: int
    truncated: bool
    summary: str = ""
    requires_fresh_tools: Literal[True] = True


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _now_text(now: datetime | None = None) -> str:
    return (now or business_now()).isoformat(timespec="seconds")


def _expiry_text(days: int, now: datetime | None = None) -> str:
    return _now_text((now or business_now()) + timedelta(days=days))


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _request_hash(role: str, text: str) -> str:
    return _hash_text(
        json.dumps(
            {"role": role, "text": text},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def _validate_idempotency_key(value: str) -> str:
    normalized = value.strip()
    if _IDEMPOTENCY_KEY.fullmatch(normalized) is None:
        raise ConversationValidationError("幂等键格式无效。")
    return normalized


def validate_persistable_text(
    value: str,
    *,
    max_chars: int,
    field_name: str,
) -> str:
    normalized = value.strip()
    if not normalized:
        raise ConversationValidationError(f"{field_name}不能为空。")
    if len(normalized) > max_chars:
        raise ConversationValidationError(f"{field_name}不能超过 {max_chars} 个字符。")
    if any(pattern.search(normalized) for pattern in _SECRET_PATTERNS):
        raise ConversationValidationError(
            f"{field_name}疑似包含密码、令牌或密钥，不能写入持久会话。"
        )
    return normalized


def _user_has_factory(user: AuthContext, factory_scope: str) -> bool:
    return factory_scope in ALLOWED_FACTORY_IDS and (
        "*" in user.factory_scopes or factory_scope in user.factory_scopes
    )


def _require_factory(user: AuthContext, factory_scope: str) -> str:
    normalized = factory_scope.strip()
    if not _user_has_factory(user, normalized):
        raise ConversationValidationError("当前账号无该厂区的会话权限。")
    return normalized


def _cursor_encode(values: list[str]) -> str:
    payload = json.dumps(values, ensure_ascii=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _cursor_decode(value: str | None, expected: int) -> tuple[str, ...] | None:
    if value is None:
        return None
    try:
        padded = value + "=" * (-len(value) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise ConversationValidationError("游标无效。") from exc
    if (
        not isinstance(decoded, list)
        or len(decoded) != expected
        or any(not isinstance(item, str) or not item for item in decoded)
    ):
        raise ConversationValidationError("游标无效。")
    return tuple(decoded)


def _parse_timestamp(value: str) -> datetime:
    parsed = parse_business_timestamp(value)
    if parsed is None:
        raise ConversationConflictError("会话时间状态无效。")
    return parsed


def _optional_timestamp(value: str) -> datetime | None:
    return _parse_timestamp(value) if value else None


def _safe_json_object(value: str) -> dict[str, int]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    if not isinstance(decoded, dict):
        return {}
    return {
        key: item
        for key, item in decoded.items()
        if isinstance(key, str) and isinstance(item, int) and item >= 0
    }


def _safe_evidence(value: str) -> list[AIEvidenceReferenceV1]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    result: list[AIEvidenceReferenceV1] = []
    for item in decoded[:12]:
        try:
            result.append(AIEvidenceReferenceV1.model_validate(item))
        except ValueError:
            continue
    return result


def _serialize_required_access(
    values: tuple[tuple[str, tuple[str, ...]], ...],
) -> str:
    normalized: dict[str, tuple[str, ...]] = {}
    for permission, departments in values:
        permission_code = permission.strip()
        safe_departments = tuple(
            sorted(
                {
                    item.strip()
                    for item in departments
                    if item.strip() and len(item.strip()) <= 64
                }
            )
        )
        if (
            not re.fullmatch(r"[a-z][a-z0-9_]*:[a-z][a-z0-9_]*", permission_code)
            or not safe_departments
        ):
            raise ConversationValidationError("Assistant 授权引用无效。")
        normalized[permission_code] = safe_departments
    return json.dumps(
        [
            {"permission": permission, "departments": list(departments)}
            for permission, departments in sorted(normalized.items())
        ],
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_required_access(
    value: str,
) -> tuple[tuple[str, tuple[str, ...]], ...] | None:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return None
    if not isinstance(decoded, list) or len(decoded) > 32:
        return None
    result: list[tuple[str, tuple[str, ...]]] = []
    for item in decoded:
        if not isinstance(item, dict) or set(item) != {"permission", "departments"}:
            return None
        permission = item.get("permission")
        departments = item.get("departments")
        if (
            not isinstance(permission, str)
            or not re.fullmatch(r"[a-z][a-z0-9_]*:[a-z][a-z0-9_]*", permission)
            or not isinstance(departments, list)
            or not departments
            or any(
                not isinstance(department, str)
                or not department
                or len(department) > 64
                for department in departments
            )
        ):
            return None
        result.append((permission, tuple(departments)))
    return tuple(result)


def _body_is_currently_authorized(
    *,
    required_access_json: str,
    user: AuthContext,
    factory_scope: str,
) -> bool:
    required_access = _parse_required_access(required_access_json)
    if required_access is None:
        return False
    return all(
        any(
            authorization_decision(
                user,
                permission,
                factory_scope,
                department,
            )[0]
            for department in departments
        )
        for permission, departments in required_access
    )


def context_binding_data(
    record: AIConversationContextBindingRecord | None,
) -> AIConversationContextBinding | None:
    if record is None:
        return None
    return AIConversationContextBinding(
        factory_scope=record.factory_scope,
        module_id=record.module_id,
        route_name=record.route_name,
        path=record.path,
        context_version=record.context_version,
        selected_entity_type=record.selected_entity_type,
        selected_entity_id=record.selected_entity_id,
        selected_entity_revision=record.selected_entity_revision,
        updated_at=_parse_timestamp(record.updated_at),
    )


def get_context_binding(
    db: Session,
    *,
    conversation_id: str,
) -> AIConversationContextBindingRecord | None:
    return db.get(AIConversationContextBindingRecord, conversation_id)


def bound_page_context(
    db: Session,
    *,
    conversation_id: str,
) -> AIPageContextInput | None:
    binding = get_context_binding(db, conversation_id=conversation_id)
    if binding is None:
        return None
    selected_entity = (
        AISelectedEntityInput(
            type=binding.selected_entity_type,
            id=binding.selected_entity_id,
            revision=binding.selected_entity_revision,
        )
        if binding.selected_entity_type
        and binding.selected_entity_id
        and binding.selected_entity_revision is not None
        else None
    )
    return AIPageContextInput(
        route_name=binding.route_name,
        path=binding.path,
        factory_id=binding.factory_scope,
        module_id=binding.module_id,
        selected_entity=selected_entity,
    )


def conversation_list_item(
    record: AIConversation,
    *,
    context_binding: AIConversationContextBindingRecord | None = None,
) -> AIConversationListItem:
    return AIConversationListItem(
        id=record.id,
        mode=record.mode,
        status=record.status,
        title=record.title,
        factory_scope=record.factory_scope,
        revision=record.revision,
        created_at=_parse_timestamp(record.created_at),
        updated_at=_parse_timestamp(record.updated_at),
        expires_at=_optional_timestamp(record.expires_at),
        message_count=record.message_count,
        last_message_at=_optional_timestamp(record.last_message_at),
        pinned_at=_optional_timestamp(record.pinned_at),
        archived_at=_optional_timestamp(record.archived_at),
        context_binding=context_binding_data(context_binding),
    )


def message_data(
    record: AIMessage,
    *,
    persisted: bool = True,
) -> AIConversationMessageData:
    return AIConversationMessageData(
        id=record.id,
        conversation_id=record.conversation_id,
        role=record.role,
        kind=record.kind,
        text=record.body,
        authority=record.authority,
        requires_tool_refresh=bool(record.requires_tool_refresh),
        persisted=persisted,
        truncated=bool(record.truncated),
        skill_id=record.skill_id,
        skill_version=record.skill_version,
        skill_hash=record.skill_hash,
        prompt_version=record.prompt_version,
        prompt_hash=record.prompt_hash,
        provider_profile=record.provider_profile,
        provider_model_alias=record.provider_model_alias,
        usage=_safe_json_object(record.usage_json),
        evidence=_safe_evidence(record.evidence_json),
        created_at=_parse_timestamp(record.created_at),
        expires_at=_optional_timestamp(record.expires_at),
    )


def summary_data(record: AIConversationSummary) -> AIConversationSummaryData:
    return AIConversationSummaryData(
        id=record.id,
        kind=record.kind,
        text=record.body,
        authority=record.authority,
        requires_tool_refresh=bool(record.requires_tool_refresh),
        source_message_count=record.source_message_count,
        prompt_version=record.prompt_version,
        prompt_hash=record.prompt_hash,
        created_at=_parse_timestamp(record.created_at),
        expires_at=_parse_timestamp(record.expires_at),
    )


def create_conversation(
    db: Session,
    *,
    payload: AIConversationCreate,
    user: AuthContext,
    settings: Settings,
    now: datetime | None = None,
) -> AIConversation:
    current = now or business_now()
    factory_scope = _require_factory(user, payload.factory_scope)
    mode = payload.mode.value
    if mode == "TEMPORARY":
        title = "临时会话"
    elif payload.title:
        title = validate_persistable_text(
            payload.title,
            max_chars=MAX_TITLE_CHARS,
            field_name="会话标题",
        )
    else:
        title = "新会话"
    created_at = _now_text(current)
    record = AIConversation(
        id=_id("aicv"),
        owner_user_id=user.id,
        factory_scope=factory_scope,
        mode=mode,
        status="ACTIVE",
        title=title,
        revision=1,
        message_count=0,
        next_message_ordinal=1,
        created_at=created_at,
        updated_at=created_at,
        last_message_at="",
        expires_at=(
            _expiry_text(settings.ai_conversation_message_retention_days, current)
            if mode == "TEMPORARY"
            else ""
        ),
        title_expires_at=_expiry_text(
            settings.ai_conversation_message_retention_days,
            current,
        ),
        deleted_at="",
        tombstone_expires_at="",
        last_idempotency_key="",
        last_request_hash="",
        last_ephemeral_message_id="",
        pinned_at="",
        archived_at="",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def list_conversations(
    db: Session,
    *,
    user: AuthContext,
    limit: int = 20,
    cursor: str | None = None,
    allowed_factory_scopes: frozenset[str] | None = None,
) -> AIConversationListPage:
    if not 1 <= limit <= MAX_LIST_PAGE:
        raise ConversationValidationError("分页大小无效。")
    cursor_values = _cursor_decode(cursor, 2)
    query = select(AIConversation).where(
        AIConversation.owner_user_id == user.id,
        AIConversation.status == "ACTIVE",
    )
    allowed_factories = (
        set(ALLOWED_FACTORY_IDS)
        if "*" in user.factory_scopes
        else set(user.factory_scopes).intersection(ALLOWED_FACTORY_IDS)
    )
    if allowed_factory_scopes is not None:
        allowed_factories.intersection_update(allowed_factory_scopes)
    if "*" not in user.factory_scopes or allowed_factory_scopes is not None:
        if not allowed_factories:
            return AIConversationListPage(items=[], next_cursor=None)
        query = query.where(AIConversation.factory_scope.in_(allowed_factories))
    if cursor_values is not None:
        updated_at, record_id = cursor_values
        query = query.where(
            or_(
                AIConversation.updated_at < updated_at,
                and_(
                    AIConversation.updated_at == updated_at,
                    AIConversation.id < record_id,
                ),
            )
        )
    rows = list(
        db.scalars(
            query.order_by(
                AIConversation.updated_at.desc(), AIConversation.id.desc()
            ).limit(limit + 1)
        ).all()
    )
    has_more = len(rows) > limit
    visible = rows[:limit]
    next_cursor = (
        _cursor_encode([visible[-1].updated_at, visible[-1].id])
        if has_more and visible
        else None
    )
    bindings = (
        {
            item.conversation_id: item
            for item in db.scalars(
                select(AIConversationContextBindingRecord).where(
                    AIConversationContextBindingRecord.conversation_id.in_(
                        [item.id for item in visible]
                    )
                )
            ).all()
        }
        if visible
        else {}
    )
    return AIConversationListPage(
        items=[
            conversation_list_item(item, context_binding=bindings.get(item.id))
            for item in visible
        ],
        next_cursor=next_cursor,
    )


def get_owned_conversation(
    db: Session,
    *,
    conversation_id: str,
    user: AuthContext,
    active_only: bool = True,
) -> AIConversation:
    if _OPAQUE_ID.fullmatch(conversation_id) is None:
        raise ConversationNotFoundError("会话不存在。")
    query = select(AIConversation).where(
        AIConversation.id == conversation_id,
        AIConversation.owner_user_id == user.id,
    )
    if active_only:
        query = query.where(AIConversation.status == "ACTIVE")
    record = db.scalar(query)
    if record is None or not _user_has_factory(user, record.factory_scope):
        raise ConversationNotFoundError("会话不存在。")
    return record


def get_conversation_detail(
    db: Session,
    *,
    conversation_id: str,
    user: AuthContext,
    message_limit: int = 50,
    message_cursor: str | None = None,
    now: datetime | None = None,
) -> AIConversationDetail:
    if not 1 <= message_limit <= MAX_DETAIL_MESSAGES:
        raise ConversationValidationError("消息分页大小无效。")
    record = get_owned_conversation(
        db,
        conversation_id=conversation_id,
        user=user,
    )
    current_text = _now_text(now)
    cursor_values = _cursor_decode(message_cursor, 2)
    query = select(AIMessage).where(
        AIMessage.conversation_id == record.id,
        AIMessage.expires_at > current_text,
    )
    if cursor_values is not None:
        ordinal_text, message_id = cursor_values
        try:
            ordinal = int(ordinal_text)
        except ValueError as exc:
            raise ConversationValidationError("消息游标无效。") from exc
        query = query.where(
            or_(
                AIMessage.ordinal < ordinal,
                and_(AIMessage.ordinal == ordinal, AIMessage.id < message_id),
            )
        )
    rows = list(
        db.scalars(
            query.order_by(AIMessage.ordinal.desc(), AIMessage.id.desc()).limit(
                message_limit + 1
            )
        ).all()
    )
    has_more = len(rows) > message_limit
    selected = rows[:message_limit]
    next_cursor = (
        _cursor_encode([str(selected[-1].ordinal), selected[-1].id])
        if has_more and selected
        else None
    )
    selected = [
        item
        for item in selected
        if _body_is_currently_authorized(
            required_access_json=item.required_access_json,
            user=user,
            factory_scope=record.factory_scope,
        )
    ]
    selected.reverse()
    summaries = list(
        db.scalars(
            select(AIConversationSummary)
            .where(
                AIConversationSummary.conversation_id == record.id,
                AIConversationSummary.expires_at > current_text,
            )
            .order_by(
                AIConversationSummary.created_at.desc(),
                AIConversationSummary.id.desc(),
            )
            .limit(12)
        ).all()
    )
    summary = next(
        (
            item
            for item in summaries
            if _body_is_currently_authorized(
                required_access_json=item.required_access_json,
                user=user,
                factory_scope=record.factory_scope,
            )
        ),
        None,
    )
    base = conversation_list_item(
        record,
        context_binding=get_context_binding(db, conversation_id=record.id),
    ).model_dump()
    return AIConversationDetail(
        **base,
        messages=[message_data(item) for item in selected],
        summary=summary_data(summary) if summary is not None else None,
        next_message_cursor=next_cursor,
    )


def _ephemeral_message(
    *,
    record: AIConversation,
    message_id: str,
    role: str,
    body: str,
    now: datetime,
) -> AIConversationMessageData:
    return AIConversationMessageData(
        id=message_id,
        conversation_id=record.id,
        role=role,
        kind="TEXT",
        text=body,
        authority="CONVERSATIONAL_ONLY",
        requires_tool_refresh=True,
        persisted=False,
        created_at=now,
        expires_at=_optional_timestamp(record.expires_at),
    )


def append_user_message(
    db: Session,
    *,
    conversation_id: str,
    payload: AIConversationMessageCreate,
    user: AuthContext,
    settings: Settings,
    now: datetime | None = None,
) -> AIConversationMessageData:
    record = get_owned_conversation(
        db,
        conversation_id=conversation_id,
        user=user,
    )
    current = now or business_now()
    text = payload.text.strip()
    if not text or len(text) > MAX_MESSAGE_CHARS:
        raise ConversationValidationError("消息正文为空或超过 8000 个字符。")
    if record.mode == "PERSISTENT":
        text = validate_persistable_text(
            text,
            max_chars=MAX_MESSAGE_CHARS,
            field_name="消息正文",
        )
    idempotency_key = _validate_idempotency_key(payload.idempotency_key)
    request_hash = _request_hash("USER", text)
    if record.mode == "TEMPORARY":
        if record.last_idempotency_key == idempotency_key:
            if record.last_request_hash != request_hash:
                raise ConversationConflictError("幂等键已用于不同消息。")
            return _ephemeral_message(
                record=record,
                message_id=record.last_ephemeral_message_id,
                role="USER",
                body=text,
                now=_parse_timestamp(record.last_message_at),
            )
    else:
        existing = db.scalar(
            select(AIMessage).where(
                AIMessage.conversation_id == record.id,
                AIMessage.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            if existing.request_hash != request_hash:
                raise ConversationConflictError("幂等键已用于不同消息。")
            return message_data(existing)
    if (
        payload.expected_revision is not None
        and payload.expected_revision != record.revision
    ):
        raise ConversationStaleError("会话已更新，请刷新后重试。")

    created_at = _now_text(current)
    message_id = _id("aimsg")
    if record.mode == "TEMPORARY":
        record.last_idempotency_key = idempotency_key
        record.last_request_hash = request_hash
        record.last_ephemeral_message_id = message_id
        record.last_message_at = created_at
        record.updated_at = created_at
        record.revision += 1
        db.commit()
        return _ephemeral_message(
            record=record,
            message_id=message_id,
            role="USER",
            body=text,
            now=current,
        )

    message = AIMessage(
        id=message_id,
        conversation_id=record.id,
        ordinal=record.next_message_ordinal,
        role="USER",
        kind="TEXT",
        body=text,
        body_sha256=_hash_text(text),
        authority="CONVERSATIONAL_ONLY",
        requires_tool_refresh=1,
        truncated=0,
        skill_id="",
        skill_version="",
        skill_hash="",
        prompt_version="",
        prompt_hash="",
        provider_profile="",
        provider_model_alias="",
        usage_json="{}",
        evidence_json="[]",
        required_access_json="[]",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        created_at=created_at,
        expires_at=_expiry_text(
            settings.ai_conversation_message_retention_days,
            current,
        ),
    )
    db.add(message)
    record.next_message_ordinal += 1
    record.message_count += 1
    record.last_message_at = created_at
    record.updated_at = created_at
    record.revision += 1
    db.commit()
    return message_data(message)


def append_assistant_message(
    db: Session,
    *,
    conversation_id: str,
    user: AuthContext,
    text: str,
    idempotency_key: str,
    settings: Settings,
    metadata: AssistantMessageMetadata | None = None,
    now: datetime | None = None,
) -> AIConversationMessageData:
    record = get_owned_conversation(
        db,
        conversation_id=conversation_id,
        user=user,
    )
    current = now or business_now()
    normalized = text.strip()
    if not normalized:
        raise ConversationValidationError("Assistant 消息不能为空。")
    blocked = any(pattern.search(normalized) for pattern in _SECRET_PATTERNS)
    if record.mode == "PERSISTENT" and blocked:
        raise ConversationValidationError("Assistant 消息疑似包含秘密，不能持久化。")
    truncated = len(normalized) > MAX_MESSAGE_CHARS
    body = normalized[:MAX_MESSAGE_CHARS]
    key = _validate_idempotency_key(idempotency_key)
    request_hash = _request_hash("ASSISTANT", body)
    if record.mode == "TEMPORARY":
        return _ephemeral_message(
            record=record,
            message_id=_id("aimsg"),
            role="ASSISTANT",
            body=body,
            now=current,
        )
    existing = db.scalar(
        select(AIMessage).where(
            AIMessage.conversation_id == record.id,
            AIMessage.idempotency_key == key,
        )
    )
    if existing is not None:
        if existing.request_hash != request_hash:
            raise ConversationConflictError("幂等键已用于不同消息。")
        return message_data(existing)

    safe = metadata or AssistantMessageMetadata()
    evidence_json = json.dumps(
        [item.model_dump(mode="json") for item in safe.evidence[:12]],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    usage_json = json.dumps(
        {
            key: value
            for key, value in (safe.usage or {}).items()
            if key in {"input_tokens", "output_tokens", "total_tokens"}
            and isinstance(value, int)
            and value >= 0
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    required_access_json = _serialize_required_access(safe.required_access)
    created_at = _now_text(current)
    message = AIMessage(
        id=_id("aimsg"),
        conversation_id=record.id,
        ordinal=record.next_message_ordinal,
        role="ASSISTANT",
        kind="TEXT",
        body=body,
        body_sha256=_hash_text(body),
        authority="CONVERSATIONAL_ONLY",
        requires_tool_refresh=1,
        truncated=int(truncated),
        skill_id=safe.skill_id[:128],
        skill_version=safe.skill_version[:64],
        skill_hash=safe.skill_hash[:64],
        prompt_version=safe.prompt_version[:128],
        prompt_hash=safe.prompt_hash[:64],
        provider_profile=safe.provider_profile[:128],
        provider_model_alias=safe.provider_model_alias[:128],
        usage_json=usage_json,
        evidence_json=evidence_json,
        required_access_json=required_access_json,
        idempotency_key=key,
        request_hash=request_hash,
        created_at=created_at,
        expires_at=_expiry_text(
            settings.ai_conversation_message_retention_days,
            current,
        ),
    )
    db.add(message)
    record.next_message_ordinal += 1
    record.message_count += 1
    record.last_message_at = created_at
    record.updated_at = created_at
    record.revision += 1
    db.commit()
    return message_data(message)


def create_safe_summary(
    db: Session,
    *,
    conversation_id: str,
    user: AuthContext,
    text: str,
    source_message_count: int,
    prompt_version: str,
    prompt_hash: str,
    settings: Settings,
    now: datetime | None = None,
) -> AIConversationSummary:
    record = get_owned_conversation(
        db,
        conversation_id=conversation_id,
        user=user,
    )
    if record.mode != "PERSISTENT":
        raise ConversationConflictError("临时会话不能保存摘要。")
    body = validate_persistable_text(
        text,
        max_chars=MAX_SUMMARY_CHARS,
        field_name="受控摘要",
    )
    if source_message_count < 0 or source_message_count > record.message_count:
        raise ConversationValidationError("摘要来源消息数量无效。")
    if not re.fullmatch(r"[0-9a-f]{64}", prompt_hash):
        raise ConversationValidationError("摘要 Prompt 哈希无效。")
    current = now or business_now()
    source_access_rows = db.scalars(
        select(AIMessage.required_access_json).where(
            AIMessage.conversation_id == record.id,
            AIMessage.role == "ASSISTANT",
        )
    ).all()
    required_access_values: set[tuple[str, tuple[str, ...]]] = set()
    for raw_access in source_access_rows:
        parsed_access = _parse_required_access(raw_access)
        if parsed_access is None:
            raise ConversationConflictError("摘要来源授权元数据无效。")
        required_access_values.update(parsed_access)
    summary = AIConversationSummary(
        id=_id("aisum"),
        conversation_id=record.id,
        kind="SAFE_STAGE_SUMMARY",
        body=body,
        body_sha256=_hash_text(body),
        authority="CONVERSATIONAL_ONLY",
        requires_tool_refresh=1,
        source_message_count=source_message_count,
        prompt_version=prompt_version[:128],
        prompt_hash=prompt_hash,
        required_access_json=_serialize_required_access(
            tuple(sorted(required_access_values))
        ),
        created_at=_now_text(current),
        expires_at=_expiry_text(
            settings.ai_conversation_summary_retention_days,
            current,
        ),
    )
    db.add(summary)
    db.commit()
    return summary


def assemble_conversation_history(
    db: Session,
    *,
    conversation_id: str,
    user: AuthContext,
    settings: Settings,
    reserve_messages: int = 1,
    reserve_chars: int = 0,
    now: datetime | None = None,
) -> ConversationHistory:
    record = get_owned_conversation(
        db,
        conversation_id=conversation_id,
        user=user,
    )
    if record.mode == "TEMPORARY":
        return ConversationHistory(
            conversation_id=record.id,
            messages=(),
            message_count=0,
            input_chars=0,
            truncated=False,
        )
    current_text = _now_text(now)
    message_budget = max(
        0,
        min(settings.ai_max_input_messages, MAX_HISTORY_MESSAGES) - reserve_messages,
    )
    char_budget = max(
        0,
        min(settings.ai_max_input_chars, MAX_HISTORY_CHARS) - reserve_chars,
    )
    candidates = list(
        db.scalars(
            select(AIMessage)
            .where(
                AIMessage.conversation_id == record.id,
                AIMessage.expires_at > current_text,
            )
            .order_by(AIMessage.ordinal.desc(), AIMessage.id.desc())
            .limit(MAX_DETAIL_MESSAGES)
        ).all()
    )
    selected: list[AIMessage] = []
    used_chars = 0
    authorized_candidates = [
        item
        for item in candidates
        if _body_is_currently_authorized(
            required_access_json=item.required_access_json,
            user=user,
            factory_scope=record.factory_scope,
        )
    ]
    truncated = len(authorized_candidates) > message_budget
    for item in authorized_candidates[:message_budget]:
        if len(item.body) > settings.ai_max_input_message_chars:
            truncated = True
            continue
        if used_chars + len(item.body) > char_budget:
            truncated = True
            break
        selected.append(item)
        used_chars += len(item.body)
    selected.reverse()
    summaries = list(
        db.scalars(
            select(AIConversationSummary)
            .where(
                AIConversationSummary.conversation_id == record.id,
                AIConversationSummary.expires_at > current_text,
            )
            .order_by(
                AIConversationSummary.created_at.desc(),
                AIConversationSummary.id.desc(),
            )
            .limit(12)
        ).all()
    )
    summary = next(
        (
            item
            for item in summaries
            if _body_is_currently_authorized(
                required_access_json=item.required_access_json,
                user=user,
                factory_scope=record.factory_scope,
            )
        ),
        None,
    )
    summary_text = summary.body if summary is not None else ""
    return ConversationHistory(
        conversation_id=record.id,
        messages=tuple(
            ProviderMessage(
                role="user" if item.role == "USER" else "assistant",
                content=item.body,
            )
            for item in selected
        ),
        message_count=len(selected),
        input_chars=used_chars,
        truncated=truncated,
        summary=summary_text,
    )


def update_conversation_context(
    db: Session,
    *,
    conversation_id: str,
    payload: AIConversationContextUpdate,
    user: AuthContext,
    settings: Settings,
    now: datetime | None = None,
) -> AIConversationContextBinding | None:
    """Persist a context hint only after current IAM and entity reauthorization."""

    record = get_owned_conversation(
        db,
        conversation_id=conversation_id,
        user=user,
    )
    if (
        payload.expected_revision is not None
        and payload.expected_revision != record.revision
    ):
        raise ConversationStaleError("会话版本已变化，请刷新后重试。")
    current = now or business_now()
    current_text = _now_text(current)
    binding = get_context_binding(db, conversation_id=record.id)
    if payload.page_context is None:
        if binding is not None:
            db.delete(binding)
        record.updated_at = current_text
        record.revision += 1
        db.commit()
        return None
    requested = payload.page_context
    if requested.factory_id != record.factory_scope:
        raise ConversationValidationError("会话上下文不能跨厂区切换。")
    try:
        server_context = build_server_page_context(
            requested,
            user,
            db=db,
            semantic_gateway_enabled=settings.ai_semantic_gateway_enabled,
            knowledge_hub_enabled=settings.ai_knowledge_hub_enabled,
        )
    except AIPageContextValidationError as exc:
        raise ConversationValidationError(
            "当前业务上下文不可用，请刷新权限后重试。"
        ) from exc
    if (
        server_context is None
        or server_context.verified_factory_id != record.factory_scope
        or server_context.verified_module_id != requested.module_id
    ):
        raise ConversationValidationError("当前账号无该业务上下文权限。")
    selected = requested.selected_entity
    if binding is None:
        binding = AIConversationContextBindingRecord(
            conversation_id=record.id,
            factory_scope=record.factory_scope,
            module_id=requested.module_id,
            route_name=requested.route_name,
            path=requested.path,
            context_version=1,
            selected_entity_type=selected.type if selected is not None else "",
            selected_entity_id=selected.id if selected is not None else "",
            selected_entity_revision=selected.revision
            if selected is not None
            else None,
            created_at=current_text,
            updated_at=current_text,
        )
        db.add(binding)
    else:
        binding.factory_scope = record.factory_scope
        binding.module_id = requested.module_id
        binding.route_name = requested.route_name
        binding.path = requested.path
        binding.context_version += 1
        binding.selected_entity_type = selected.type if selected is not None else ""
        binding.selected_entity_id = selected.id if selected is not None else ""
        binding.selected_entity_revision = (
            selected.revision if selected is not None else None
        )
        binding.updated_at = current_text
    record.updated_at = current_text
    record.revision += 1
    db.commit()
    db.refresh(binding)
    return context_binding_data(binding)


def update_conversation(
    db: Session,
    *,
    conversation_id: str,
    payload: AIConversationUpdate,
    user: AuthContext,
    now: datetime | None = None,
) -> AIConversationListItem:
    record = get_owned_conversation(
        db,
        conversation_id=conversation_id,
        user=user,
    )
    if (
        payload.expected_revision is not None
        and payload.expected_revision != record.revision
    ):
        raise ConversationStaleError("会话版本已变化，请刷新后重试。")
    current_text = _now_text(now)
    if payload.title is not None:
        record.title = validate_persistable_text(
            payload.title,
            max_chars=MAX_TITLE_CHARS,
            field_name="会话标题",
        )
    if payload.pinned is not None:
        record.pinned_at = current_text if payload.pinned else ""
    if payload.archived is not None:
        record.archived_at = current_text if payload.archived else ""
        if payload.archived:
            record.pinned_at = ""
    record.updated_at = current_text
    record.revision += 1
    db.commit()
    db.refresh(record)
    return conversation_list_item(
        record,
        context_binding=get_context_binding(db, conversation_id=record.id),
    )


def delete_conversation(
    db: Session,
    *,
    conversation_id: str,
    user: AuthContext,
    settings: Settings,
    now: datetime | None = None,
) -> bool:
    if _OPAQUE_ID.fullmatch(conversation_id) is None:
        return False
    record = db.scalar(
        select(AIConversation).where(
            AIConversation.id == conversation_id,
            AIConversation.owner_user_id == user.id,
        )
    )
    if record is None or not _user_has_factory(user, record.factory_scope):
        return False
    if record.status == "DELETED":
        return True
    current = now or business_now()
    db.query(AIMessage).filter(AIMessage.conversation_id == record.id).delete(
        synchronize_session=False
    )
    db.query(AIConversationSummary).filter(
        AIConversationSummary.conversation_id == record.id
    ).delete(synchronize_session=False)
    record.status = "DELETED"
    record.title = ""
    record.message_count = 0
    record.deleted_at = _now_text(current)
    record.tombstone_expires_at = _expiry_text(
        settings.ai_conversation_tombstone_retention_days,
        current,
    )
    record.updated_at = record.deleted_at
    record.last_message_at = ""
    record.last_idempotency_key = ""
    record.last_request_hash = ""
    record.last_ephemeral_message_id = ""
    record.revision += 1
    db.commit()
    return True
