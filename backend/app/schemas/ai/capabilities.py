from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai.context import AIPageContextInput


class AIPilotAccessCapability(BaseModel):
    granted: bool
    status: Literal[
        "DISABLED",
        "TLS_REQUIRED",
        "CONTROL_REQUIRED",
        "PROVIDER_REQUIRED",
        "GRANTED",
    ]
    read_only: bool
    max_tool_risk_level: Literal["READ_ONLY", "PREVIEW_WITH_AUDIT"]


class AICapabilities(BaseModel):
    enabled: bool
    available: bool
    provider: str
    model: str
    streaming: bool
    vision_enabled: bool
    conversation_persistence: bool = False
    artifact_workflows_enabled: bool | None = None
    vision_tool_comparison_enabled: bool | None = None
    feedback_enabled: bool | None = None
    tool_groups: list[str] = Field(default_factory=list)
    pilot_access: AIPilotAccessCapability


class AICapabilityContextRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_context: AIPageContextInput | None = None


class AINIFCapabilities(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["2"] = "2"
    platform_supported: bool = True
    configured_enabled: bool
    runtime_available: bool
    user_allowed: bool
    context_status: Literal["MISSING", "INVALID", "ALLOWED", "DENIED"]
    reason_code: str
    provider: str
    model: str
    provider_profile: str = ""
    catalog_version: str = ""
    model_capabilities: list[str] = Field(default_factory=list)
    reasoning_policies: list[str] = Field(default_factory=list)
    streaming: bool
    vision_enabled: bool
    feature_flags: dict[str, bool]
    available_tool_groups: list[str] = Field(default_factory=list)
    available_tools: list[str] = Field(default_factory=list)
    available_skills: list[str] = Field(default_factory=list)
    max_autonomy_level: Literal["L0", "L1", "L2"] = "L0"
