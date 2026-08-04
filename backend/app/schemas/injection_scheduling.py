from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MachineStatus = Literal["available", "running", "maintenance", "offline"]
MoldStatus = Literal[
    "available",
    "maintenance",
    "not_arrived",
    "occupied",
    "retired",
]
DataQualityStatus = Literal["complete", "needs_review"]
NormalizationStatus = Literal["COMPLETE", "REVIEW_REQUIRED"]


class InjectionSchedulingMachineData(BaseModel):
    machine_code: str = Field(min_length=1, max_length=64)
    area: str = Field(default="", max_length=128)
    position: str = Field(default="", max_length=128)
    machine_class: str = Field(default="", max_length=64)
    machine_class_raw: str = Field(default="", max_length=128)
    machine_a_class: float | None = Field(default=None, gt=0)
    normalization_status: NormalizationStatus = "REVIEW_REQUIRED"
    process_tags: list[str] = Field(default_factory=list, max_length=32)
    special_machine_type: str = Field(default="", max_length=64)
    clamping_force_tons: float | None = Field(default=None, gt=0)
    injection_capacity_g: float | None = Field(default=None, gt=0)
    tie_bar_x_mm: float | None = Field(default=None, gt=0)
    tie_bar_y_mm: float | None = Field(default=None, gt=0)
    platen_x_mm: float | None = Field(default=None, gt=0)
    platen_y_mm: float | None = Field(default=None, gt=0)
    min_mold_thickness_mm: float | None = Field(default=None, gt=0)
    max_mold_thickness_mm: float | None = Field(default=None, gt=0)
    opening_stroke_mm: float | None = Field(default=None, gt=0)
    machine_type: str = Field(default="standard", max_length=64)
    robot_capabilities: list[str] = Field(default_factory=list, max_length=32)
    fixture_capabilities: list[str] = Field(default_factory=list, max_length=64)
    process_restrictions: list[str] = Field(default_factory=list, max_length=64)
    status: MachineStatus = "available"

    @field_validator(
        "machine_code",
        "area",
        "position",
        "machine_class",
        "machine_class_raw",
        "machine_type",
        "special_machine_type",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "robot_capabilities",
        "fixture_capabilities",
        "process_restrictions",
        "process_tags",
    )
    @classmethod
    def normalize_capabilities(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("能力或限制代码不能重复")
        return normalized

    @model_validator(mode="after")
    def validate_mold_thickness_range(self):
        if (
            self.min_mold_thickness_mm is not None
            and self.max_mold_thickness_mm is not None
            and self.min_mold_thickness_mm > self.max_mold_thickness_mm
        ):
            raise ValueError("最小模厚不能大于最大模厚")
        return self


class InjectionSchedulingMachineCreate(InjectionSchedulingMachineData):
    factory_id: str
    expected_revision: Literal[0] = 0


class InjectionSchedulingMachineUpdate(InjectionSchedulingMachineData):
    factory_id: str
    expected_revision: int = Field(ge=1)


class InjectionSchedulingMachineOut(InjectionSchedulingMachineData):
    model_config = ConfigDict(from_attributes=True)

    id: str
    factory_id: str
    revision: int
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    created_at: str
    updated_at: str


class InjectionSchedulingMachineListOut(BaseModel):
    factory_id: str
    items: list[InjectionSchedulingMachineOut]


class InjectionSchedulingMoldData(BaseModel):
    mold_no: str = Field(min_length=1, max_length=128)
    name: str = Field(default="", max_length=255)
    length_mm: float | None = Field(default=None, gt=0)
    width_mm: float | None = Field(default=None, gt=0)
    height_mm: float | None = Field(default=None, gt=0)
    weight_kg: float | None = Field(default=None, gt=0)
    recommended_machine_class: str = Field(default="", max_length=64)
    mold_class_raw: str = Field(default="", max_length=128)
    mold_a_class: float | None = Field(default=None, gt=0)
    normalization_status: NormalizationStatus = "REVIEW_REQUIRED"
    process_tags: list[str] = Field(default_factory=list, max_length=32)
    special_machine_type: str = Field(default="", max_length=64)
    whole_shot_net_weight_g: float | None = Field(default=None, gt=0)
    whole_shot_gross_weight_g: float | None = Field(default=None, gt=0)
    required_arm_type: str = Field(default="", max_length=64)
    required_fixture_type: str = Field(default="", max_length=128)
    material_code: str = Field(default="", max_length=128)
    material_name: str = Field(default="", max_length=255)
    color_profile: str = Field(default="", max_length=128)
    process_requirements: list[str] = Field(default_factory=list, max_length=64)
    copy_count: int = Field(default=1, ge=1, le=100)
    data_quality_status: DataQualityStatus = "needs_review"
    status: MoldStatus = "available"

    @field_validator(
        "mold_no",
        "name",
        "recommended_machine_class",
        "mold_class_raw",
        "required_arm_type",
        "required_fixture_type",
        "material_code",
        "material_name",
        "color_profile",
        "special_machine_type",
    )
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("process_requirements", "process_tags")
    @classmethod
    def normalize_requirements(cls, values: list[str]) -> list[str]:
        normalized = [value.strip() for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("工艺要求代码不能重复")
        return normalized

    @model_validator(mode="after")
    def validate_weight_and_quality(self):
        if (
            self.whole_shot_net_weight_g is not None
            and self.whole_shot_gross_weight_g is not None
            and self.whole_shot_net_weight_g > self.whole_shot_gross_weight_g
        ):
            raise ValueError("整啤净重不能大于整啤毛重")
        return self


class InjectionSchedulingMoldCreate(InjectionSchedulingMoldData):
    factory_id: str
    expected_revision: Literal[0] = 0


class InjectionSchedulingMoldUpdate(InjectionSchedulingMoldData):
    factory_id: str
    expected_revision: int = Field(ge=1)


class InjectionSchedulingMoldOut(InjectionSchedulingMoldData):
    id: str
    factory_id: str
    revision: int
    created_by: str
    created_by_name: str
    updated_by: str
    updated_by_name: str
    created_at: str
    updated_at: str


class InjectionSchedulingMoldListOut(BaseModel):
    factory_id: str
    items: list[InjectionSchedulingMoldOut]


class InjectionSchedulingRuleConfig(BaseModel):
    schema_version: str = Field(default="phase0-v2", min_length=1, max_length=64)
    arm_coverage: dict[str, list[str]] = Field(default_factory=dict)
    process_rule_codes: list[str] = Field(default_factory=list)
    scoring_weights: dict[str, float] = Field(default_factory=dict)
    color_scale: list[str] = Field(default_factory=list)
    notes: str = Field(default="", max_length=2000)


class InjectionSchedulingRuleSetUpdate(BaseModel):
    factory_id: str
    expected_revision: int = Field(ge=1)
    configured_max_utilization: float = Field(gt=0, le=1)
    allow_mold_rotation_90: bool = False
    config: InjectionSchedulingRuleConfig


class InjectionSchedulingRuleSetOut(BaseModel):
    id: str
    factory_id: str
    revision: int
    status: Literal["active", "superseded"]
    configured_max_utilization: float
    allow_mold_rotation_90: bool
    config: dict[str, Any]
    created_by: str
    created_by_name: str
    created_at: str
    superseded_at: str
