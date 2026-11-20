from datetime import datetime
from typing import Literal
from pydantic import Field, field_validator, model_validator
from app.schemas.identity import AssignmentRole, FactoryScope, IdentityChange, NewAssignment, StrictModel
from app.schemas.position_review import Position


class StudioPackage(AssignmentRole):
    factory_scope: FactoryScope

    @model_validator(mode="after")
    def explicit_scope(self):
        scope = self.factory_scope
        if (scope.kind == "selected") != bool(scope.factory_ids) or len(set(scope.factory_ids)) != len(scope.factory_ids):
            raise ValueError("请确认每个权限包的业务厂区")
        return self


class BindingScopeEdit(StrictModel):
    binding_id: str = Field(min_length=1, max_length=128)
    factory_ids: list[str] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_factories(self):
        if len(set(self.factory_ids)) != len(self.factory_ids):
            raise ValueError("每个厂区仅可选择一次")
        return self


class OverrideAddition(StrictModel):
    permission_code: str = Field(min_length=1, max_length=128)
    effect: Literal["allow", "deny"]
    factory_id: str = Field(min_length=1, max_length=64)
    department: str = Field(min_length=1, max_length=64)
    valid_until: str | None = None

    @field_validator("valid_until")
    @classmethod
    def require_zoned_expiry(cls, value):
        if not value:
            return None
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("例外结束时间须包含时区")
        return value


class PackageEdits(StrictModel):
    add_packages: list[StudioPackage] = Field(default_factory=list, max_length=20)
    remove_binding_ids: list[str] = Field(default_factory=list, max_length=120)
    upgrade_binding_ids: list[str] = Field(default_factory=list, max_length=120)
    scope_updates: list[BindingScopeEdit] = Field(default_factory=list, max_length=120)
    add_overrides: list[OverrideAddition] = Field(default_factory=list, max_length=20)
    end_override_ids: list[str] = Field(default_factory=list, max_length=120)

    @model_validator(mode="after")
    def unique_edits(self):
        ids = self.remove_binding_ids + self.upgrade_binding_ids + [s.binding_id for s in self.scope_updates]
        if len(ids) != len(set(ids)) or any(not item or len(item) > 128 for item in ids):
            raise ValueError("请选择不同的有效绑定")
        if len(self.end_override_ids) != len(set(self.end_override_ids)):
            raise ValueError("请选择不同的个人例外来源")
        if len({(role.role_id, role.department) for role in self.add_packages}) != len(self.add_packages):
            raise ValueError("同一作用部门的权限包请合并选择厂区")
        return self


class PositionReviewLink(StrictModel):
    item_key: str = Field(pattern=r"^position:[^/]+$", max_length=128)
    expected_source_revision: str = Field(min_length=1, max_length=128)
    confirmed_profile: Position


class LegacyConfirmation(IdentityChange):
    request_type: Literal["confirm_identity"]

    @model_validator(mode="after")
    def preserve_sources(self):
        if (self.effective_at or self.source_assignment_id or self.display_name or self.official_position_title
                or self.new_assignment.role_bindings or self.new_assignment.valid_until
                or self.new_assignment.assignment_type != "regular"):
            raise ValueError("首次核实仅确认原有授权来源和正式主职")
        return self


class StudioDraft(PackageEdits):
    position_review: PositionReviewLink | None = None
    official_posting: Position | None = None
    base_identity_version: int = Field(ge=0)
    base_authorization_version: int = Field(ge=0)
    source_assignment_id: str = Field(min_length=1, max_length=96)
    official_position_title: str | None = Field(default=None, min_length=1, max_length=128)
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason", "official_position_title", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class StudioChange(IdentityChange):
    # Only the studio constructs this command. Public legacy draft endpoints
    # still accept their original, strictly validated union.
    request_type: Literal["adjust_packages"]
    package_delta: PackageEdits
    position_review: PositionReviewLink | None = None
    official_posting: Position | None = None


class StudioAssignment(NewAssignment):
    role_bindings: list[StudioPackage] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def unique_packages(self):
        if len({(r.role_id, r.department) for r in self.role_bindings}) != len(self.role_bindings):
            raise ValueError("请合并同一作用部门权限包的业务厂区")
        return self


class StudioLifecycle(IdentityChange):
    request_type: Literal["add_assignment", "end_assignment", "freeze", "unfreeze", "leave", "rehire"]
    new_assignment: StudioAssignment | None = None

    @model_validator(mode="after")
    def single_operation(self):
        if (self.effective_at or self.binding_dispositions or self.exception_decisions or self.display_name
                or self.official_position_title or (self.request_type != "end_assignment" and self.source_assignment_id)):
            raise ValueError("单项办理仅接受本次任职、明确选择的权限包或账号状态")
        return self


class StudioCommit(StrictModel):
    preview_token: str = Field(min_length=1, max_length=256)
    risk_acknowledged: bool = False
    confirm_empty_packages: bool = False
