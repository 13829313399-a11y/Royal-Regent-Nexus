from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PageContext(Strict):
    module_id: str = Field(max_length=64)
    route_name: str = Field(max_length=80)
    factory_id: str | None = Field(default=None, max_length=32)
    help_id: str | None = Field(default=None, max_length=96)


class CreateSession(Strict):
    client_request_id: str = Field(min_length=8, max_length=64)


class RenameSession(Strict):
    title: str = Field(min_length=1, max_length=160)
    revision: int = Field(ge=1)


class ResourceRef(Strict):
    module_id: str = Field(max_length=64)
    resource_type: str = Field(max_length=64)
    resource_id: str = Field(max_length=160)
    revision: str | None = Field(default=None, max_length=80)


class ContextSelection(Strict):
    selection_id: str = Field(max_length=96)
    resources: list[ResourceRef] = Field(default_factory=list, max_length=10)
    filters: dict[str, str | int | bool | None] = Field(default_factory=dict, max_length=12)


class RunRelation(Strict):
    parent_run_id: str = Field(min_length=1, max_length=64)
    kind: Literal["revise", "regenerate", "excerpt", "retry"]


class SendMessage(Strict):
    protocol_version: Literal[1, 2, 3] = 1
    client_request_id: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1, max_length=200000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=8)
    document_ids: list[str] = Field(default_factory=list, max_length=8)
    context_selection: ContextSelection | None = None
    intent: Literal["chat", "explain_page", "explain_element", "my_work", "research", "analyze_files"] = "chat"
    profile_id: Literal["default"] = "default"
    thinking: Literal["auto", "on", "off"] = "auto"
    web_search: Literal["off", "on", "auto"] = "off"
    page_context: PageContext | None = None
    relation: RunRelation | None = None

    @model_validator(mode="after")
    def version_contract(self):
        if self.protocol_version == 1 and (self.document_ids or self.context_selection or
                self.intent not in ("chat", "explain_page", "explain_element") or self.web_search == "auto" or self.relation):
            raise ValueError("v2 required for new material or intent")
        return self


def canonical_request(payload: SendMessage):
    frozen = payload.model_dump(mode="json")
    # Preserve hashes for every existing v1 and v2 idempotency request.
    if payload.relation is None:
        frozen.pop("relation", None)
    if payload.protocol_version == 1:
        for key in ("protocol_version", "document_ids", "context_selection"):
            frozen.pop(key, None)
    return frozen


class ArtifactCreate(Strict):
    source_run_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=160)
    kind: Literal["research", "markdown", "checklist", "table", "chart"] = "markdown"
    content: str = Field(min_length=1, max_length=200000)


class ArtifactVersion(Strict):
    base_revision: int = Field(ge=1)
    content: str = Field(min_length=1, max_length=200000)


class FavoritePatch(Strict):
    favorite: bool


class DocumentSearch(Strict):
    document_ids: list[str] = Field(min_length=1, max_length=8)
    query: str = Field(min_length=1, max_length=2000)


class DocumentReplacement(Strict):
    replacement_id: str = Field(min_length=1,max_length=64)
    expected_version: str = Field(pattern=r'^[a-f0-9]{64}$')
    replacement_version: str = Field(pattern=r'^[a-f0-9]{64}$')


class ActionRequest(Strict):
    run_id: str = Field(min_length=1, max_length=64)
    index: int = Field(ge=0, le=100)


class FeedbackPut(Strict):
    client_request_id: str = Field(min_length=8,max_length=64)
    base_revision: int = Field(ge=0)
    categories: list[Literal['factual','off_topic','sources','experience']] = Field(default_factory=list,max_length=4)
    source_ids: list[str] = Field(default_factory=list,max_length=32)
    comment: str = Field(default='',max_length=2000)

    @model_validator(mode='after')
    def feedback_content(self):
        if not self.categories and not self.comment.strip():
            raise ValueError('choose a category or add a comment')
        if len(set(self.categories))!=len(self.categories) or len(set(self.source_ids))!=len(self.source_ids):
            raise ValueError('duplicate category or source')
        if any(not ident or len(ident)>96 for ident in self.source_ids):
            raise ValueError('invalid source ID')
        return self


class SubscriptionReceipt(Strict):
    applied_seq: int = Field(ge=0)
