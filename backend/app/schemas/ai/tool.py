from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AIToolRiskLevel(StrEnum):
    READ_ONLY = "READ_ONLY"
    PREVIEW_WITH_AUDIT = "PREVIEW_WITH_AUDIT"
    CONSEQUENTIAL_WRITE = "CONSEQUENTIAL_WRITE"
    HIGH_RISK_WRITE = "HIGH_RISK_WRITE"


class AIToolAuditPolicy(StrEnum):
    METADATA_ONLY = "METADATA_ONLY"
    SECURITY_DENIALS = "SECURITY_DENIALS"
    NONE = "NONE"


class AIToolErrorCode(StrEnum):
    UNKNOWN_TOOL = "AI_TOOL_UNKNOWN"
    INVALID_ARGUMENTS = "AI_TOOL_INVALID_ARGUMENTS"
    RISK_NOT_ALLOWED = "AI_TOOL_RISK_NOT_ALLOWED"
    INVALID_FACTORY = "AI_TOOL_INVALID_FACTORY"
    DEPARTMENT_NOT_ALLOWED = "AI_TOOL_DEPARTMENT_NOT_ALLOWED"
    PERMISSION_DENIED = "AI_TOOL_PERMISSION_DENIED"
    TIMEOUT = "AI_TOOL_TIMEOUT"
    RESULT_ROWS_EXCEEDED = "AI_TOOL_RESULT_ROWS_EXCEEDED"
    RESULT_BYTES_EXCEEDED = "AI_TOOL_RESULT_BYTES_EXCEEDED"
    RESULT_FIELDS_EXCEEDED = "AI_TOOL_RESULT_FIELDS_EXCEEDED"
    INVALID_RESULT = "AI_TOOL_INVALID_RESULT"
    EXECUTION_FAILED = "AI_TOOL_EXECUTION_FAILED"


class StrictToolInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class AIToolError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: AIToolErrorCode
    message: str
    retryable: bool = False


class AIToolResultMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    row_count: int = Field(default=0, ge=0)
    field_count: int = Field(default=0, ge=0)
    truncated: bool = False


class AIToolResultEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    tool_name: str
    data: object | None = None
    error: AIToolError | None = None
    metadata: AIToolResultMetadata = Field(default_factory=AIToolResultMetadata)

    @model_validator(mode="after")
    def validate_outcome(self) -> "AIToolResultEnvelope":
        if self.ok and self.error is not None:
            raise ValueError("successful tool results cannot contain an error")
        if not self.ok and self.error is None:
            raise ValueError("failed tool results must contain an error")
        if not self.ok and self.data is not None:
            raise ValueError("failed tool results cannot contain data")
        return self
