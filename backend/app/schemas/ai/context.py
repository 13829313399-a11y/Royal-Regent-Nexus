from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

AIPageRouteName = Literal[
    "injection-scheduling-v2",
    "internal-quote-desk-home",
    "molding-sample",
    "carton-procurement",
    "raw-material-management",
    "customer-order-center",
    "ai-workbench",
]
AIPagePath = Literal[
    "/modules/production/injection-scheduling",
    "/modules/sales-business/internal-quote-desk",
    "/modules/molding-sample",
    "/modules/pmc-warehouse/carton-procurement",
    "/modules/pmc-warehouse/raw-material-management",
    "/modules/sales-business/po-schedule-intake",
    "/workbench/ai",
]
AIPageModuleId = Literal[
    "injection-scheduling",
    "internal-quote",
    "molding-sample",
    "carton-procurement",
    "raw-material",
    "customer-order",
    "ai-workbench",
]
AIKnowledgeId = Literal[
    "injection-scheduling",
    "internal-quote",
    "molding-sample",
    "carton-procurement",
    "raw-material",
    "customer-order",
    "ai-usage",
]


class AIPageContextInput(BaseModel):
    """Client page hint. Every field is revalidated before provider use."""

    model_config = ConfigDict(extra="forbid")

    route_name: AIPageRouteName
    path: AIPagePath
    factory_id: str | None = Field(default=None, min_length=1, max_length=32)
    module_id: AIPageModuleId
    selected_entity: "AISelectedEntityInput | None" = None


class AISelectedEntityInput(BaseModel):
    """Untrusted client reference; no entity payload is accepted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["scheduling_backlog_order", "internal_quote"]
    id: str = Field(
        min_length=1,
        max_length=96,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,95}$",
    )
    revision: int = Field(ge=1)


class AIServerSelectedEntity(BaseModel):
    """Current, authorized and field-minimized server projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    type: Literal["scheduling_backlog_order", "internal_quote"]
    id: str
    revision: int = Field(ge=1)
    display_label: str = Field(min_length=1, max_length=255)
    source_type: Literal["FORMAL"] = "FORMAL"


class AIServerPageContext(BaseModel):
    """Small, server-owned page context safe to expose to the model/tools."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    verified_route_name: AIPageRouteName
    verified_path: AIPagePath
    verified_factory_id: str | None = None
    verified_module_id: AIPageModuleId
    knowledge_id: AIKnowledgeId
    allowed_tool_groups: tuple[str, ...]
    selected_entity: AIServerSelectedEntity | None = None


AIPageContextInput.model_rebuild()
