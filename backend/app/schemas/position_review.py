from typing import Literal
from uuid import UUID
from pydantic import Field, field_validator, model_validator
from app.schemas.identity import StrictModel, FactoryScope, ExceptionDecision


class Position(StrictModel):
    org_unit_id: str = Field(min_length=1, max_length=64)
    department_code: str = Field(min_length=1, max_length=64)
    position: str = Field(min_length=1, max_length=128)

    @field_validator("org_unit_id", "department_code", "position", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class Declaration(Position):
    requested_role_ids: list[str] = Field(default_factory=list, max_length=3)
    requested_factory_ids: list[str] = Field(default_factory=list, max_length=6)
    note: str = Field(default="", max_length=1000)

    @field_validator("requested_role_ids", "requested_factory_ids")
    @classmethod
    def distinct_references(cls, values):
        if len(set(values)) != len(values) or any(not value or len(value) > 64 for value in values):
            raise ValueError("参考选项无效或重复")
        return values

    def snapshot(self):
        return self.model_dump(exclude={key for key in ("requested_role_ids", "requested_factory_ids")
                                        if not getattr(self, key)})

    @field_validator("note", mode="before")
    @classmethod
    def trim_note(cls, value):
        return value.strip() if isinstance(value, str) else value


class SubmitReview(StrictModel):
    declaration: Declaration


class UpdateReview(SubmitReview):
    expected_revision: int = Field(ge=1)


class WithdrawReview(StrictModel):
    expected_revision: int = Field(ge=1)


class RegistrationDetails(StrictModel):
    display_name: str = Field(min_length=1, max_length=128)
    phone: str = Field(default="", max_length=64)
    email: str = Field(default="", max_length=128)

    @field_validator("display_name", "phone", "email", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def contact(self):
        if not self.phone and not self.email:
            raise ValueError("手机或邮箱至少填写一项")
        return self


class PackageSelection(StrictModel):
    role_id: str = Field(min_length=1, max_length=64)
    definition_hash: str = Field(min_length=1, max_length=64)
    role_version_id: str | None = None
    factory_scope: FactoryScope
    permission_department: str = Field(min_length=1, max_length=64)


class PreviewInput(StrictModel):
    expected_source_revision: str = Field(min_length=1, max_length=128)
    decision: Literal["apply_package", "keep_permissions"]
    confirmed_profile: Position
    package_selection: PackageSelection | None = None
    package_selections: list[PackageSelection] = Field(default_factory=list, max_length=20)
    independent_allow_decisions: list[ExceptionDecision] = Field(max_length=200)
    registration_details_correction: RegistrationDetails | None = None

    @property
    def selected_packages(self):
        return [self.package_selection] if self.package_selection else self.package_selections

    @model_validator(mode="after")
    def shape(self):
        if self.package_selection and self.package_selections:
            raise ValueError("请使用一种权限包选择方式")
        if len({p.role_id for p in self.selected_packages}) != len(self.selected_packages):
            raise ValueError("权限包重复，请在同一个包中选择厂区")
        if (self.decision == "apply_package") != bool(self.selected_packages):
            raise ValueError("请选择方案；保留权限时不能同时选择新方案")
        if len({d.override_id for d in self.independent_allow_decisions}) != len(self.independent_allow_decisions):
            raise ValueError("独立授权处置重复")
        return self


class CommitInput(StrictModel):
    expected_source_revision: str = Field(min_length=1, max_length=128)
    preview_token: str = Field(min_length=1, max_length=256)
    command_id: UUID
    risk_acknowledged: bool


class DecisionInput(StrictModel):
    expected_source_revision: str = Field(min_length=1, max_length=128)
    command_id: UUID
    action: Literal["return_position", "reject_registration"]
    reason: str = Field(min_length=1, max_length=2000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim(cls, value):
        return value.strip() if isinstance(value, str) else value


class AdminAdjustment(StrictModel):
    target_user_id: str = Field(min_length=1, max_length=64)
    proposed_profile: Position
    reason: str = Field(min_length=1, max_length=2000)
