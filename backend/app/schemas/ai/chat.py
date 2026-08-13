from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.ai.artifact import AIArtifactEgressConsent, AIArtifactReferenceInput
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
    conversation_id: str | None = Field(
        default=None,
        pattern=r"^aicv-[0-9a-f]{32}$",
        exclude=True,
    )
    page_context: AIPageContextInput | None = None
    attachments: list[AIImageAttachmentInput] = Field(
        default_factory=list,
        max_length=3,
    )
    cloud_processing_consent: AICloudProcessingConsent | None = None
    artifact_attachments: list[AIArtifactReferenceInput] = Field(
        default_factory=list,
        max_length=3,
        exclude=True,
    )
    artifact_egress_consent: AIArtifactEgressConsent | None = Field(
        default=None,
        exclude=True,
    )

    @model_validator(mode="after")
    def validate_attachment_contract(self):
        if self.attachments and self.artifact_attachments:
            raise ValueError("raw and Artifact image inputs cannot be mixed")
        if self.artifact_attachments:
            consent = self.artifact_egress_consent
            artifact_ids = [item.artifact_id for item in self.artifact_attachments]
            if (
                self.cloud_processing_consent is not None
                or consent is None
                or consent.content_class != "IMAGE"
                or consent.artifact_ids != artifact_ids
            ):
                raise ValueError("Artifact image consent is missing or mismatched")
        elif self.artifact_egress_consent is not None:
            raise ValueError("Artifact consent requires Artifact image inputs")
        return self


class AIStreamEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    request_id: str
    sequence: int = Field(ge=1)
    type: AIStreamEventType
    timestamp: str
    payload: dict[str, object] = Field(default_factory=dict)
