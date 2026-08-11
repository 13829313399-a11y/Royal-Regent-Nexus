from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.ai.tool import StrictToolInput

PriorityCode = Literal["NORMAL", "URGENT", "CRITICAL"]
BacklogSourceScope = Literal["PLANNING_DRAFT", "GLOBAL_BACKLOG"]


class InjectionSchedulingPlanContextInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)


class InjectionSchedulingBacklogInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=100_000)


class AIEntityLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    route: str
    query: dict[str, str]


class AIInjectionSchedulingPlanSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    business_date: str
    status_code: Literal["PUBLISHED", "DRAFT"]
    business_label: str
    revision: int = Field(ge=1)
    task_count: int = Field(ge=0)
    running_count: int = Field(default=0, ge=0)


class AIInjectionSchedulingPlanContextData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["FORMAL"] = "FORMAL"
    factory_id: str
    as_of: str
    execution_published: AIInjectionSchedulingPlanSummary | None
    planning_draft: AIInjectionSchedulingPlanSummary | None
    polling_revision: int = Field(ge=0)
    entity_links: list[AIEntityLink]


class AIInjectionSchedulingBacklogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_id: str
    order_no: str
    item_no: str
    product_name: str
    mold_no: str
    priority_code: PriorityCode
    priority_business_label: str
    delivery_due_date: str
    order_quantity: float = Field(ge=0)
    outstanding_quantity: float = Field(ge=0)
    mold_enrichment_status: str
    mold_enrichment_business_label: str
    source_type: str


class AIInjectionSchedulingBacklogData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_type: Literal["FORMAL"] = "FORMAL"
    factory_id: str
    as_of: str
    source_scope: BacklogSourceScope
    source_business_label: str
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=50)
    offset: int = Field(ge=0)
    returned: int = Field(ge=0)
    truncated: bool
    items: list[AIInjectionSchedulingBacklogItem]
    entity_links: list[AIEntityLink]
