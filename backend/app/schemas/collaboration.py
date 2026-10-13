from typing import Literal
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Versioned(StrictModel):
    expected_version: int = Field(ge=0)


class ProfilePatch(Versioned):
    bio: str = Field(default="", max_length=280)
    help_topics: str = Field(default="", max_length=80)
    skill_tags: list[str] = Field(default_factory=list, max_length=6)
    theme: Literal["celadon", "jade", "dusk", "champagne"] = "celadon"
    availability: Literal["available", "busy", "leave_message"] = "available"
    status_text: str = Field(default="", max_length=60)
    status_expires_at: str | None = None

    @field_validator("skill_tags")
    @classmethod
    def tags(cls, value):
        cleaned = list(dict.fromkeys(t.strip() for t in value if t.strip()))
        if any(len(t) > 20 for t in cleaned):
            raise ValueError("专长标签最多 20 字")
        return cleaned

    @field_validator("status_expires_at")
    @classmethod
    def expiry(cls, value):
        if value is None:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("必须包含时区")
        from app.services.identity_resolver import stamp
        return stamp(parsed)


class PreferencesPatch(Versioned):
    motion: Literal["rich", "simple", "off"] = "rich"
    density: Literal["comfortable", "compact"] = "comfortable"
    sound_enabled: bool = False
    read_receipts_enabled: bool = False
    dnd_until: str | None = None
    send_key: Literal["enter", "ctrl_enter"] = "enter"
    module_shortcuts: list[str] = Field(default_factory=list, max_length=6)
    _expiry = field_validator("dnd_until")(ProfilePatch.expiry.__func__)


class DirectRequest(StrictModel):
    peer_user_id: str = Field(min_length=1, max_length=64)


class Reference(StrictModel):
    resource_type: Literal["molding_sample", "internal_quote"]
    resource_id: str = Field(min_length=1, max_length=96)
    factory_id: str = Field(min_length=1, max_length=64)


class MessageRequest(StrictModel):
    client_message_id: str = Field(min_length=8, max_length=96)
    kind: Literal["text", "attachment", "business_reference"] = "text"
    body: str = Field(default="", max_length=4000)
    reply_to_id: str | None = Field(default=None, max_length=64)
    attachment_ids: list[str] = Field(default_factory=list, max_length=6)
    reference: Reference | None = None
    draft_version: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def composition(self):
        if self.kind == "text" and (not self.body.strip() or self.attachment_ids or self.reference):
            raise ValueError("文本消息须包含正文，且不可附带附件或业务引用")
        if self.kind == "attachment" and (not self.attachment_ids or self.reference):
            raise ValueError("附件消息须包含附件")
        if self.kind == "business_reference" and (self.reference is None or self.attachment_ids):
            raise ValueError("业务卡片须包含一个业务引用")
        if len(set(self.attachment_ids)) != len(self.attachment_ids):
            raise ValueError("附件不可重复")
        return self


class DraftPatch(Versioned):
    text: str = Field(default="", max_length=4000)
    reply_to_id: str | None = Field(default=None, max_length=64)
    attachment_ids: list[str] = Field(default_factory=list, max_length=6)


class ReadRequest(StrictModel):
    through_message_seq: int = Field(ge=0)


class ConversationPreferencesPatch(Versioned):
    mute_until: str | None = None
    pin_order: int = Field(default=0, ge=0, le=10000)
    archived: bool = False
    _expiry = field_validator("mute_until")(ProfilePatch.expiry.__func__)


class AppreciationRequest(StrictModel):
    client_request_id: str = Field(min_length=8, max_length=96)
    receiver_id: str = Field(min_length=1, max_length=64)
    category: Literal["timely_help", "careful_check", "patient_explanation", "problem_solved"]
    text: str = Field(min_length=1, max_length=500)


class AppreciationPatch(Versioned):
    seen: bool = False
    private_pin_order: int = Field(default=0, ge=0, le=3)
    hidden: bool = False
