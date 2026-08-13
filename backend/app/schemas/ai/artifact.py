from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.ai.attachment import AICloudConsentAccepted

AIArtifactClassification = Literal[
    "INTERNAL", "CONFIDENTIAL_BUSINESS", "RESTRICTED"
]
AIArtifactStatus = Literal["ACTIVE", "DELETION_PENDING", "DELETED", "EXPIRED"]
AIArtifactScannerStatus = Literal["CLEAN", "REJECTED"]
AIArtifactParserStatus = Literal["NOT_REQUESTED", "PENDING", "READY", "FAILED"]
AIArtifactDerivationType = Literal[
    "ORIGINAL",
    "WORKBOOK_MAPPING",
    "TRANSLATION",
    "OCR",
    "REPORT",
    "OTHER_DERIVED",
]
AIArtifactContentClass = Literal["WORKBOOK", "DOCUMENT", "IMAGE"]
AIArtifactId = Annotated[str, Field(pattern=r"^aiart-[0-9a-f]{32}$")]

_NOTICE_BY_CONTENT_CLASS = {
    "WORKBOOK": "aliyun-cn-beijing-workbook-v1",
    "DOCUMENT": "aliyun-cn-beijing-document-v1",
    "IMAGE": "aliyun-cn-beijing-image-v1",
}


class AIArtifactReferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    artifact_id: AIArtifactId


class AIArtifactEgressConsent(BaseModel):
    """Per-request consent bound to exact Artifact ids and a content class."""

    model_config = ConfigDict(extra="forbid", strict=True)

    accepted: AICloudConsentAccepted
    notice_version: Literal[
        "aliyun-cn-beijing-workbook-v1",
        "aliyun-cn-beijing-document-v1",
        "aliyun-cn-beijing-image-v1",
    ]
    provider: Literal["qwen"]
    region: Literal["cn-beijing"]
    classification: AIArtifactClassification
    content_class: AIArtifactContentClass
    artifact_ids: list[AIArtifactId] = Field(
        min_length=1,
        max_length=3,
    )

    @model_validator(mode="after")
    def validate_scope(self):
        if self.notice_version != _NOTICE_BY_CONTENT_CLASS[self.content_class]:
            raise ValueError("consent notice does not match the content class")
        if len(self.artifact_ids) != len(set(self.artifact_ids)):
            raise ValueError("consent artifact ids must be unique")
        return self


class AIArtifactData(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str = Field(pattern=r"^aiart-[0-9a-f]{32}$")
    factory_id: str
    original_filename: str
    normalized_extension: str
    declared_mime_type: str
    detected_mime_type: str
    content_class: AIArtifactContentClass
    size_bytes: int = Field(gt=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    classification: AIArtifactClassification
    status: AIArtifactStatus
    scanner_status: AIArtifactScannerStatus
    parser_status: AIArtifactParserStatus
    parent_artifact_id: str | None = None
    derivation_type: AIArtifactDerivationType
    parser_version: str = ""
    model_version: str = ""
    retention_until: str
    deleted_at: str = ""
    created_at: str
    updated_at: str


class AIArtifactDeleteData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^aiart-[0-9a-f]{32}$")
    status: Literal["DELETION_PENDING", "DELETED", "EXPIRED"]
    access_revoked: Literal[True] = True
    deleted_at: str
    online_delete_due_by: str
    backup_delete_by: str
