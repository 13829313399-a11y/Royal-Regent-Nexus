from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AIPageRouteName = Literal[
    "injection-scheduling-v2",
    "internal-quote-desk-home",
]
AIPagePath = Literal[
    "/modules/production/injection-scheduling",
    "/modules/sales-business/internal-quote-desk",
]
AIPageModuleId = Literal[
    "injection-scheduling",
    "internal-quote",
]
AIKnowledgeId = Literal[
    "injection-scheduling",
    "internal-quote",
]


class AIPageContextInput(BaseModel):
    """Client page hint. Every field is revalidated before provider use."""

    model_config = ConfigDict(extra="forbid")

    route_name: AIPageRouteName
    path: AIPagePath
    factory_id: str | None = Field(default=None, min_length=1, max_length=32)
    module_id: AIPageModuleId
    selected_entity: None = None


class AIServerPageContext(BaseModel):
    """Small, server-owned page context safe to expose to the model/tools."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verified_route_name: AIPageRouteName
    verified_path: AIPagePath
    verified_factory_id: str | None = None
    verified_module_id: AIPageModuleId
    knowledge_id: AIKnowledgeId
    allowed_tool_groups: tuple[str, ...]
