from typing import Literal

from pydantic import BaseModel, Field


class AIPilotAccessCapability(BaseModel):
    granted: bool
    status: Literal[
        "DISABLED",
        "TLS_REQUIRED",
        "CONTROL_REQUIRED",
        "PROVIDER_REQUIRED",
        "GRANTED",
    ]
    read_only: Literal[True] = True


class AICapabilities(BaseModel):
    enabled: bool
    available: bool
    provider: str
    model: str
    streaming: bool
    vision_enabled: bool
    conversation_persistence: bool = False
    tool_groups: list[str] = Field(default_factory=list)
    pilot_access: AIPilotAccessCapability
