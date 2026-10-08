from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


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


class SendMessage(Strict):
    client_request_id: str = Field(min_length=8, max_length=64)
    text: str = Field(min_length=1, max_length=200000)
    attachment_ids: list[str] = Field(default_factory=list, max_length=8)
    intent: Literal["chat", "explain_page", "explain_element"] = "chat"
    profile_id: Literal["default"] = "default"
    thinking: Literal["auto", "on", "off"] = "auto"
    web_search: Literal["off", "on"] = "off"
    page_context: PageContext | None = None
