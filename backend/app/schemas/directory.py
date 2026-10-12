from typing import Literal

from pydantic import BaseModel, Field

PresenceState = Literal["online", "away", "offline"]


class DirectoryMemberOut(BaseModel):
    id: str
    display_name: str
    position: str
    primary_factory_id: str
    primary_department: str
    avatar_url: str
    avatar_version: str
    presence_state: PresenceState
    org_unit_id: str = ""
    org_name: str = "未登记组织"
    org_kind: str = "unknown"
    self_profile: dict = Field(default_factory=dict)
    actions: dict[str, bool] = Field(default_factory=dict)
    is_contact: bool = False


class DirectoryStateCounts(BaseModel):
    online: int = 0
    away: int = 0
    offline: int = 0


class DirectorySummaryResponse(BaseModel):
    total_members: int = 0
    state_counts: DirectoryStateCounts = Field(default_factory=DirectoryStateCounts)
    preview_members: list[DirectoryMemberOut] = Field(default_factory=list)
    server_now: str = ""
    snapshot_at: str = ""


class DirectoryMembersResponse(BaseModel):
    items: list[DirectoryMemberOut] = Field(default_factory=list)
    total: int = 0
    page: int = 1
    page_size: int = 36
    total_pages: int = 0
    state_counts: DirectoryStateCounts = Field(default_factory=DirectoryStateCounts)
    server_now: str = ""
    snapshot_at: str = ""
    counts_scope: str = "matching_filters_before_presence"


class DirectoryHeartbeatResponse(BaseModel):
    status: Literal["ok"] = "ok"
    written: bool
    presence_state: Literal["online"] = "online"
