from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.ai.context import (
    AIPageContextInput,
    AIPageModuleId,
    AIPagePath,
    AIPageRouteName,
)
from app.schemas.ai.evidence import AIEvidenceReferenceV1


class AIConversationMode(StrEnum):
    PERSISTENT = "PERSISTENT"
    TEMPORARY = "TEMPORARY"


class AIConversationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    DELETION_PENDING = "DELETION_PENDING"
    DELETED = "DELETED"
    EXPIRED = "EXPIRED"


class AIConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AIConversationMode = AIConversationMode.PERSISTENT
    factory_scope: str = Field(min_length=1, max_length=64)
    title: str = Field(default="", max_length=160)

    @field_validator("factory_scope", "title")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class AIConversationContextBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factory_scope: str
    module_id: AIPageModuleId
    route_name: AIPageRouteName
    path: AIPagePath
    context_version: int = Field(ge=1)
    selected_entity_type: str = ""
    selected_entity_id: str = ""
    selected_entity_revision: int | None = Field(default=None, ge=1)
    updated_at: datetime


class AIConversationContextUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_context: AIPageContextInput | None
    expected_revision: int | None = Field(default=None, ge=1)


class AIContextOption(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factory_scope: str
    module_id: AIPageModuleId
    route_name: AIPageRouteName
    path: AIPagePath
    display_label: str = Field(min_length=1, max_length=64)
    tool_groups: list[str] = Field(default_factory=list)
    maximum_risk: Literal["PREVIEW_WITH_AUDIT"] = "PREVIEW_WITH_AUDIT"


class AIContextOptionsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AIContextOption]


class AIConversationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=160)
    pinned: bool | None = None
    archived: bool | None = None
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("title")
    @classmethod
    def strip_optional_title(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_change(self):
        if self.title is None and self.pinned is None and self.archived is None:
            raise ValueError("至少提供一个会话管理变更。")
        return self


class AIConversationMessageCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=8_000)
    idempotency_key: str = Field(min_length=8, max_length=128)
    expected_revision: int | None = Field(default=None, ge=1)

    @field_validator("text", "idempotency_key")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class AIConversationListItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    mode: AIConversationMode
    status: AIConversationStatus
    title: str
    factory_scope: str
    revision: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None
    message_count: int = Field(ge=0)
    last_message_at: datetime | None
    pinned_at: datetime | None = None
    archived_at: datetime | None = None
    context_binding: AIConversationContextBinding | None = None


class AIConversationMessageData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    conversation_id: str
    role: str
    kind: str
    text: str
    authority: str = "CONVERSATIONAL_ONLY"
    requires_tool_refresh: bool = True
    persisted: bool = True
    truncated: bool = False
    skill_id: str = ""
    skill_version: str = ""
    skill_hash: str = ""
    prompt_version: str = ""
    prompt_hash: str = ""
    provider_profile: str = ""
    provider_model_alias: str = ""
    usage: dict[str, int] = Field(default_factory=dict)
    evidence: list[AIEvidenceReferenceV1] = Field(default_factory=list)
    created_at: datetime
    expires_at: datetime | None


class AIConversationSummaryData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    text: str
    authority: str = "CONVERSATIONAL_ONLY"
    requires_tool_refresh: bool = True
    source_message_count: int = Field(ge=0)
    prompt_version: str = ""
    prompt_hash: str = ""
    created_at: datetime
    expires_at: datetime


class AIConversationDetail(AIConversationListItem):
    messages: list[AIConversationMessageData] = Field(default_factory=list)
    summary: AIConversationSummaryData | None = None
    next_message_cursor: str | None = None


class AIConversationListPage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AIConversationListItem]
    next_cursor: str | None = None


class AIConversationHistoryMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: str
    message_count: int = Field(ge=0)
    input_chars: int = Field(ge=0)
    truncated: bool
    requires_fresh_tools: bool = True
