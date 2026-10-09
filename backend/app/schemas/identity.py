from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FactoryScope(StrictModel):
    kind: Literal["home", "selected", "all_current"] = "home"
    factory_ids: list[str] = Field(default_factory=list, max_length=50)


class AssignmentRole(StrictModel):
    role_id: str = Field(min_length=1, max_length=64)
    role_version_id: str | None = None
    department: str = Field(min_length=1, max_length=64)
    factory_scope: FactoryScope = Field(default_factory=FactoryScope)


class NewAssignment(StrictModel):
    org_unit_id: str = Field(min_length=1, max_length=64)
    department_code: str = Field(min_length=1, max_length=64)
    official_position_title: str = Field(min_length=1, max_length=128)
    assignment_type: Literal["regular", "part_time", "temporary", "acting"] = "regular"
    is_primary: bool = True
    valid_until: datetime | None = None
    role_bindings: list[AssignmentRole] = Field(default_factory=list, max_length=20)

    @field_validator("valid_until")
    @classmethod
    def zoned(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("时间必须包含时区")
        return value


class ExceptionDecision(StrictModel):
    override_id: str
    decision: Literal["keep_original_scope", "end"]


class BindingDisposition(StrictModel):
    binding_id: str
    source: Literal["assignment", "system_administration", "external_collaboration", "individual_exception"]


class IdentityChange(StrictModel):
    request_type: Literal["confirm_identity", "primary_assignment_transfer", "add_assignment", "end_assignment",
                          "profile_correction", "freeze", "unfreeze", "leave", "rehire", "upgrade_packages"]
    target_user_id: str = Field(min_length=1, max_length=64)
    reason: str = Field(min_length=1, max_length=2000)
    base_identity_version: int = Field(ge=0)
    base_authorization_version: int = Field(ge=0)
    effective_at: datetime | None = None
    source_assignment_id: str | None = None
    new_assignment: NewAssignment | None = None
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    official_position_title: str | None = Field(default=None, min_length=1, max_length=128)
    exception_decisions: list[ExceptionDecision] = Field(default_factory=list, max_length=200)
    binding_dispositions: list[BindingDisposition] = Field(default_factory=list, max_length=200)

    @field_validator("effective_at")
    @classmethod
    def zoned(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("时间必须包含时区")
        return value

    @model_validator(mode="after")
    def shape(self):
        needs = self.request_type in {"confirm_identity", "primary_assignment_transfer", "add_assignment", "rehire"}
        if needs != (self.new_assignment is not None):
            raise ValueError("请按变更类型填写新任职")
        if self.request_type in {"primary_assignment_transfer", "end_assignment", "upgrade_packages"} and not self.source_assignment_id:
            raise ValueError("请选择来源任职")
        if self.request_type == "add_assignment" and self.new_assignment.is_primary:
            raise ValueError("兼任不能替换主职")
        if self.request_type in {"confirm_identity", "primary_assignment_transfer", "rehire"} and not self.new_assignment.is_primary:
            raise ValueError("此变更需要主职")
        if self.request_type == "profile_correction" and not (self.display_name or self.official_position_title):
            raise ValueError("请填写更正内容")
        if len({d.override_id for d in self.exception_decisions}) != len(self.exception_decisions):
            raise ValueError("例外处理重复")
        if len({d.binding_id for d in self.binding_dispositions}) != len(self.binding_dispositions):
            raise ValueError("来源处理重复")
        return self


class DraftUpdate(StrictModel):
    expected_request_revision: int
    change: IdentityChange


class IdentityCommit(StrictModel):
    preview_token: str = Field(min_length=1, max_length=256)
    expected_request_revision: int
    confirm_high_risk: bool = False


class IdentityDecision(StrictModel):
    expected_request_revision: int
    reason: str = Field(min_length=1, max_length=2000)


class HandoverReassign(StrictModel):
    successor_user_id: str
    expected_resource_revision: int


class BatchCommitItem(StrictModel):
    change_id: str
    idempotency_key: str = Field(min_length=1, max_length=128)
    commit: IdentityCommit


class BatchCommit(StrictModel):
    items: list[BatchCommitItem] = Field(min_length=1, max_length=50)


class DelegationUpdate(StrictModel):
    expected_revision: int = Field(ge=0)
    org_unit_id: str
    department: str
    role_ids: list[str] = Field(max_length=100)
    factory_ids: list[str] = Field(max_length=6)
    status: Literal["active", "revoked"] = "active"
    reason: str = Field(min_length=1, max_length=2000)


class AccessExplain(StrictModel):
    permission_code: str
    factory_id: str
    department: str | None = None
    at: datetime | None = None

    @field_validator("at")
    @classmethod
    def zoned(cls, value):
        if value is not None and value.tzinfo is None:
            raise ValueError("时间必须包含时区")
        return value
