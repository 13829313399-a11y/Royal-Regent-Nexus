from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.ai.tool import StrictToolInput

InternalQuoteAIStatusCode = Literal[
    "drafting",
    "section_reviewing",
    "pending_review",
    "rejected",
    "ready_for_final_review",
    "final_reviewing",
    "fully_approved",
    "exported",
    "archived",
    "unknown",
]
InternalQuoteAIStageCode = Literal[
    "COLLABORATION",
    "SECTION_REVIEW",
    "RETURNED",
    "FINAL_SUBMISSION",
    "FINAL_REVIEW",
    "RELEASED",
    "EXPORTED",
    "ARCHIVED",
    "UNKNOWN",
]
InternalQuoteAINavigationTarget = Literal["collaboration", "summary"]

# AI-B9 Internal Quote Field Policy v1. Any new field requires a separate
# security/product review; domain models and API response schemas are not reusable here.
INTERNAL_QUOTE_AI_SAFE_ITEM_FIELDS = frozenset(
    {
        "quote_id",
        "quote_no",
        "customer",
        "status_code",
        "status_label",
        "current_stage_code",
        "current_stage_label",
        "version_label",
        "updated_at",
        "navigation_target",
    }
)


class InternalQuoteSummaryListInput(StrictToolInput):
    factory_id: str = Field(min_length=1, max_length=64)
    status: Literal[
        "",
        "drafting",
        "section_reviewing",
        "pending_review",
        "rejected",
        "ready_for_final_review",
        "final_reviewing",
        "fully_approved",
        "exported",
        "archived",
    ] = ""
    keyword: str = Field(default="", max_length=64)
    limit: int = Field(default=10, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=10_000)

    @field_validator("keyword")
    @classmethod
    def strip_keyword(cls, value: str) -> str:
        return value.strip()


class AIInternalQuoteSummaryItem(BaseModel):
    """Closed output model implementing Internal Quote Field Policy v1."""

    model_config = ConfigDict(extra="forbid")

    quote_id: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
    )
    quote_no: str = Field(min_length=1, max_length=128)
    customer: str = Field(max_length=128)
    status_code: InternalQuoteAIStatusCode
    status_label: str = Field(min_length=1, max_length=32)
    current_stage_code: InternalQuoteAIStageCode
    current_stage_label: str = Field(min_length=1, max_length=64)
    version_label: str = Field(max_length=64)
    updated_at: str = Field(max_length=32)
    navigation_target: InternalQuoteAINavigationTarget


class AIInternalQuoteSummaryListData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["internal-quote-summary-v1"] = (
        "internal-quote-summary-v1"
    )
    result_type: Literal["internal_quote.summary_list"] = (
        "internal_quote.summary_list"
    )
    source_type: Literal["FORMAL"] = "FORMAL"
    factory_id: str = Field(min_length=1, max_length=64)
    as_of: str = Field(min_length=1, max_length=40)
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=20)
    offset: int = Field(ge=0, le=10_000)
    returned: int = Field(ge=0, le=20)
    truncated: bool
    quotes: list[AIInternalQuoteSummaryItem] = Field(max_length=20)
