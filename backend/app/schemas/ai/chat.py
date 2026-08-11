from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai.attachment import AICloudProcessingConsent, AIImageAttachmentInput
from app.schemas.ai.context import AIPageContextInput

AIChatRole = Literal["user", "assistant"]
AIStreamEventType = Literal[
    "response.started",
    "message.delta",
    "tool.started",
    "tool.completed",
    "message.completed",
    "warning",
    "error",
    "response.completed",
]


class AITextInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["input_text"]
    text: str = Field(min_length=1)


class AIChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: AIChatRole
    content: list[AITextInput] = Field(min_length=1, max_length=16)


class AIChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[AIChatMessage] = Field(min_length=1)
    page_context: AIPageContextInput | None = None
    attachments: list[AIImageAttachmentInput] = Field(
        default_factory=list,
        max_length=3,
    )
    cloud_processing_consent: AICloudProcessingConsent | None = None


class AIStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    request_id: str
    sequence: int = Field(ge=1)
    type: AIStreamEventType
    timestamp: str
    payload: dict[str, object] = Field(default_factory=dict)
