from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class KnowledgeLifecycle(StrEnum):
    DRAFT = "DRAFT"
    OWNER_REVIEWED = "OWNER_REVIEWED"
    SOURCE_BOUND = "SOURCE_BOUND"
    INDEXED = "INDEXED"
    PILOT_READY = "PILOT_READY"
    EVAL_PASSED = "EVAL_PASSED"
    PUBLISHED = "PUBLISHED"
    EXPIRED = "EXPIRED"
    RETIRED = "RETIRED"


class KnowledgeClassification(StrEnum):
    K1_BUSINESS_MODULE = "K1_BUSINESS_MODULE"
    K2_DEVELOPMENT = "K2_DEVELOPMENT"


class KnowledgeDeepLink(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(min_length=1, max_length=80)
    path: str = Field(
        min_length=1,
        max_length=255,
        pattern=r"^/(?:[A-Za-z0-9._~-]+/?)*$",
    )


class KnowledgeManifestEntry(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_id: str = Field(
        min_length=2,
        max_length=96,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    )
    version: str = Field(pattern=r"^[0-9]+\.[0-9]+\.[0-9]+$", max_length=32)
    owner: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[a-z][a-z0-9-]*$",
    )
    status: KnowledgeLifecycle
    reviewed_at: date
    reviewed_by: str = Field(
        min_length=2,
        max_length=96,
        pattern=r"^[a-z][a-z0-9-]*$",
    )
    expires_at: date
    classification: KnowledgeClassification
    module_id: str = Field(
        min_length=2,
        max_length=80,
        pattern=r"^[a-z][a-z0-9-]*$",
    )
    route_names: tuple[str, ...] = Field(min_length=1, max_length=8)
    source_path: str = Field(min_length=1, max_length=255)
    source_files: tuple[str, ...] = Field(min_length=1, max_length=32)
    factory_ids: tuple[str, ...] = Field(min_length=1, max_length=8)
    role_codes: tuple[str, ...] = Field(min_length=1, max_length=32)
    keywords: tuple[str, ...] = Field(min_length=2, max_length=32)
    deep_links: tuple[KnowledgeDeepLink, ...] = Field(default=(), max_length=8)
    eval_dataset_ref: str | None = Field(default=None, max_length=128)
    eval_runner_ref: str | None = Field(default=None, max_length=128)
    eval_result_ref: str | None = Field(default=None, max_length=160)
    evaluated_at: date | None = None
    evaluated_by: str | None = Field(default=None, max_length=96)

    @field_validator(
        "route_names",
        "source_files",
        "factory_ids",
        "role_codes",
        "keywords",
    )
    @classmethod
    def normalized_unique_values(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if any(not item or item != item.strip() for item in values):
            raise ValueError("Knowledge manifest lists must be normalized")
        if len(values) != len(set(values)):
            raise ValueError("Knowledge manifest lists must be unique")
        return values

    @model_validator(mode="after")
    def validate_lifecycle_evidence(self) -> KnowledgeManifestEntry:
        if self.expires_at <= self.reviewed_at:
            raise ValueError("Knowledge expiry must follow review")
        evaluation = (
            self.eval_dataset_ref,
            self.eval_runner_ref,
            self.eval_result_ref,
            self.evaluated_at,
            self.evaluated_by,
        )
        if self.status in {
            KnowledgeLifecycle.EVAL_PASSED,
            KnowledgeLifecycle.PUBLISHED,
        } and any(item is None for item in evaluation):
            raise ValueError("Evaluated Knowledge requires Dataset and Runner evidence")
        if self.status not in {
            KnowledgeLifecycle.EVAL_PASSED,
            KnowledgeLifecycle.PUBLISHED,
        } and any(item is not None for item in evaluation):
            raise ValueError("Unevaluated Knowledge cannot claim evaluation evidence")
        return self

    def effective_status(self, on_date: date) -> KnowledgeLifecycle:
        if self.status is KnowledgeLifecycle.RETIRED:
            return self.status
        if on_date > self.expires_at:
            return KnowledgeLifecycle.EXPIRED
        return self.status


class KnowledgeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["knowledge-manifest-v1"]
    documents: tuple[KnowledgeManifestEntry, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode="after")
    def validate_unique_ids_routes_and_sources(self) -> KnowledgeManifest:
        ids = [item.knowledge_id for item in self.documents]
        if len(ids) != len(set(ids)):
            raise ValueError("Knowledge IDs must be unique")
        routes = [route for item in self.documents for route in item.route_names]
        if len(routes) != len(set(routes)):
            raise ValueError("Knowledge routes must map to one document")
        sources = [item.source_path for item in self.documents]
        if len(sources) != len(set(sources)):
            raise ValueError("Knowledge source paths must be unique")
        return self


class KnowledgeSection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    section_id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=80)
    heading: str = Field(min_length=1, max_length=160)
    body_markdown: str = Field(min_length=1, max_length=8_000)
    normalized_text: str = Field(min_length=1, max_length=8_000)
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class KnowledgeDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    manifest: KnowledgeManifestEntry
    title: str = Field(min_length=1, max_length=160)
    sections: tuple[KnowledgeSection, ...] = Field(min_length=1, max_length=32)
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class KnowledgeCitation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    knowledge_id: str
    version: str
    section_id: str
    source_path: str
    heading: str
    reviewed_at: date
    content_hash: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class KnowledgeHit(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    score: int = Field(ge=1, le=1_000)
    text_markdown: str = Field(min_length=1, max_length=8_000)
    citation: KnowledgeCitation
    deep_links: tuple[KnowledgeDeepLink, ...] = Field(default=(), max_length=8)


class KnowledgeSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_type: Literal["VERSIONED_MODULE_KNOWLEDGE"] = (
        "VERSIONED_MODULE_KNOWLEDGE"
    )
    result_type: Literal["knowledge.search_results"] = "knowledge.search_results"
    schema_version: Literal["knowledge-search-v1"] = "knowledge-search-v1"
    authority: Literal["PROCESS_GUIDANCE"] = "PROCESS_GUIDANCE"
    conflict_policy: Literal["FORMAL_TOOL_WINS"] = "FORMAL_TOOL_WINS"
    query: str = Field(max_length=200)
    evidence_missing: bool
    message: str = Field(min_length=1, max_length=240)
    hits: tuple[KnowledgeHit, ...] = Field(max_length=5)
    truncated: bool = False
