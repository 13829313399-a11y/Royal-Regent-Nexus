from pydantic import BaseModel, Field


class RoleAssignmentRequest(BaseModel):
    role_id: str
    factory_id: str
    department: str


class RegistrationProfileCorrection(BaseModel):
    display_name: str = Field(min_length=1, max_length=128)
    phone: str = Field(default="", max_length=64)
    email: str = Field(default="", max_length=128)
    factory_id: str = Field(min_length=1, max_length=64)
    department: str = Field(min_length=1, max_length=64)
    position: str = Field(min_length=1, max_length=128)


class RegistrationApproveRequest(BaseModel):
    role_assignments: list[RoleAssignmentRequest] = Field(default_factory=list)
    system_position_role_id: str = Field(default="", max_length=64)
    profile: RegistrationProfileCorrection | None = None
    review_comment: str = ""
    position: str | None = None


class RegistrationRejectRequest(BaseModel):
    review_comment: str


class UserStatusUpdateRequest(BaseModel):
    status: str


class PasswordResetReviewRequest(BaseModel):
    review_comment: str = Field(min_length=1, max_length=1000)


class SystemNotificationUpdateRequest(BaseModel):
    status: str


class RoleOut(BaseModel):
    id: str
    code: str
    name: str
    description: str
    applicable_departments: list[str] = Field(default_factory=list)
    requires_global_factory: bool = False
    scope_guidance: str = ""
    is_system_position: bool = False
    position_department: str = ""
    position_department_name: str = ""
    position_sort_order: int = 0
    permission_count: int = 0


class UserRoleAssignmentOut(BaseModel):
    id: str
    role_id: str
    role_name: str
    role_code: str
    factory_id: str
    department: str


class RegistrationRequestOut(BaseModel):
    id: str
    user_id: str
    username: str
    display_name: str
    phone: str
    email: str
    factory_id: str
    department: str
    position: str
    status: str
    reviewer_user_id: str
    review_comment: str
    submitted_at: str
    reviewed_at: str
    created_at: str
    updated_at: str
    recommended_role_ids: list[str]


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    phone: str
    email: str
    status: str
    force_password_change: bool
    last_login_at: str
    created_at: str
    updated_at: str
    roles: list[UserRoleAssignmentOut]
    avatar_url: str = ""
    primary_factory_id: str = ""
    primary_department: str = ""
    position: str = ""
    system_position_role_id: str = ""
    system_position_role_name: str = ""


class PasswordResetMatchedUserOut(BaseModel):
    id: str
    username: str
    display_name: str
    status: str
    factory_id: str = ""
    department: str = ""
    position: str = ""
    phone: str = ""
    email: str = ""


class PasswordResetRequestOut(BaseModel):
    id: str
    user_id: str | None = None
    username: str
    display_name: str
    contact: str
    note: str
    factory_id: str
    department: str
    status: str
    reviewer_user_id: str | None = None
    review_comment: str
    notification_id: str | None = None
    submitted_at: str
    approved_at: str
    expires_at: str
    completed_at: str
    rejected_at: str
    created_at: str
    updated_at: str
    issue_count: int
    matched_user: PasswordResetMatchedUserOut | None = None
    match_checks: dict[str, bool] = Field(default_factory=dict)


class PasswordResetApproveOut(BaseModel):
    request: PasswordResetRequestOut
    temporary_password: str
    expires_at: str


class SystemNotificationOut(BaseModel):
    id: str
    target_user_id: str
    target_permission: str
    target_factory_id: str
    target_department: str
    type: str
    title: str
    message: str
    payload: dict[str, object]
    status: str
    created_at: str
    read_at: str
    handled_at: str
