from typing import Literal

from pydantic import BaseModel, Field


OverrideEffect = Literal["inherit", "allow", "deny"]


class PermissionOut(BaseModel):
    code: str
    name: str
    description: str = ""
    module_code: str
    module_name: str
    action: str
    risk_level: str
    scope_type: str
    status: str
    sort_order: int = 0
    applicable_departments: list[str] = Field(default_factory=list)
    requires_global_factory: bool = False
    scope_guidance: str = ""


class ManageableScopeOut(BaseModel):
    factory_id: str
    factory_name: str
    department: str
    department_name: str


class ManageableScopesResponse(BaseModel):
    is_super_admin: bool
    can_manage_role_templates: bool
    can_review_access_requests: bool
    scopes: list[ManageableScopeOut]


class EmployeeProfileOut(BaseModel):
    primary_factory_id: str = ""
    primary_department: str = ""
    position: str = ""
    confirmation_status: str = "pending_confirmation"


class RoleBindingOut(BaseModel):
    id: str
    role_id: str
    role_code: str
    role_name: str
    factory_id: str
    department: str
    state: str
    source_type: str
    valid_from: str = ""
    valid_until: str = ""
    reason: str = ""


class PermissionOverrideOut(BaseModel):
    id: str
    permission_id: str
    permission_code: str
    effect: str
    factory_id: str
    department: str
    state: str
    valid_from: str = ""
    valid_until: str = ""
    reason: str = ""


class EffectiveAccessOut(BaseModel):
    permission_code: str
    factory_id: str
    department: str
    allowed: bool
    effect: str
    source_type: str
    source_ids: list[str] = Field(default_factory=list)
    source_name: str = ""


class UserAccessUserOut(BaseModel):
    id: str
    username: str
    display_name: str
    status: str
    phone: str = ""
    email: str = ""


class UserAccessOut(BaseModel):
    user: UserAccessUserOut
    profile: EmployeeProfileOut | None
    authorization_version: int
    role_bindings: list[RoleBindingOut]
    overrides: list[PermissionOverrideOut]
    effective_access: list[EffectiveAccessOut]


class RoleBindingChange(BaseModel):
    operation: Literal["add", "update", "revoke"]
    binding_id: str = ""
    role_id: str = ""
    factory_id: str
    department: str
    valid_until: str | None = None


class PermissionOverrideChange(BaseModel):
    permission_code: str
    effect: OverrideEffect
    factory_id: str
    department: str
    valid_until: str | None = None


class AccessScopeInput(BaseModel):
    factory_id: str
    department: str


class UserAccessDraft(BaseModel):
    role_bindings: list[RoleBindingChange] = Field(default_factory=list)
    overrides: list[PermissionOverrideChange] = Field(default_factory=list)


class UserAccessPreviewRequest(BaseModel):
    base_revision: int = Field(ge=0)
    reason: str = Field(min_length=1, max_length=500)
    scope: AccessScopeInput | None = None
    draft: UserAccessDraft | None = None
    role_bindings: list[RoleBindingChange] = Field(default_factory=list)
    overrides: list[PermissionOverrideChange] = Field(default_factory=list)
    binding_changes: list[RoleBindingChange] = Field(default_factory=list)
    override_changes: list[PermissionOverrideChange] = Field(default_factory=list)


class AccessDiffOut(BaseModel):
    permission_code: str
    factory_id: str
    department: str
    before: str
    after: str
    before_source: str = ""
    after_source: str = ""
    risk_level: str


class AccessPreviewResponse(BaseModel):
    preview_token: str
    expires_at: str
    base_revision: int
    requires_approval: bool
    high_risk: bool
    diffs: list[AccessDiffOut]


class AccessCommitRequest(BaseModel):
    preview_token: str = Field(min_length=1)
    confirm_high_risk: bool = False


class AccessCommitResponse(BaseModel):
    status: Literal["committed", "pending_approval"]
    authorization_version: int
    request_id: str = ""
    message: str = ""


class RoleSummaryOut(BaseModel):
    id: str
    code: str
    name: str
    description: str
    version: int
    is_protected: bool
    binding_count: int
    permission_count: int
    applicable_departments: list[str] = Field(default_factory=list)
    requires_global_factory: bool = False
    scope_guidance: str = ""


class RoleAccessOut(BaseModel):
    id: str
    code: str
    name: str
    description: str
    version: int
    is_protected: bool
    binding_count: int
    permission_count: int
    permission_codes: list[str]
    applicable_departments: list[str] = Field(default_factory=list)
    requires_global_factory: bool = False
    scope_guidance: str = ""


class RoleAccessPreviewRequest(BaseModel):
    base_version: int = Field(ge=0)
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=1000)
    permission_codes: list[str]
    reason: str = Field(min_length=1, max_length=500)


class RolePermissionDiffOut(BaseModel):
    permission_code: str
    before: bool
    after: bool
    risk_level: str


class RoleAccessPreviewResponse(BaseModel):
    preview_token: str
    expires_at: str
    base_version: int
    affected_user_count: int
    diffs: list[RolePermissionDiffOut]
    high_risk: bool


class RoleAccessCommitResponse(BaseModel):
    status: Literal["committed"] = "committed"
    authorization_version: int
    request_id: str = ""
    message: str = ""


class AccessRequestCreate(BaseModel):
    preview_token: str = Field(min_length=1)
    confirm_high_risk: bool = False


class AccessRequestDecision(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class AccessRequestOut(BaseModel):
    id: str
    requester_user_id: str
    requester_name: str
    target_user_id: str
    target_user_name: str
    base_revision: int
    reason: str
    status: str
    review_reason: str = ""
    high_risk: bool
    created_at: str
    reviewed_at: str = ""
    changes: list[PermissionOverrideChange] = Field(default_factory=list)


class AuditEventOut(BaseModel):
    id: str
    event_type: str
    actor_user_id: str
    actor_name: str
    target_user_id: str
    target_user_name: str
    permission_code: str
    factory_id: str
    department: str
    reason: str
    before_value: object | None = None
    after_value: object | None = None
    request_id: str
    ip_address: str
    created_at: str


class UserSearchOut(BaseModel):
    id: str
    username: str
    display_name: str
    status: str
    primary_factory_id: str
    primary_department: str
    position: str
    manageable: bool
