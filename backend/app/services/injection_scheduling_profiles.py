from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

AuthorityType = Literal[
    "SOURCE_FACT",
    "BASELINE_DECISION",
    "SYSTEM_DERIVED",
    "LEGACY_DISPLAY",
]


@dataclass(frozen=True, slots=True)
class CanonicalField:
    name: str
    data_type: str
    authority: AuthorityType
    usage: str


@dataclass(frozen=True, slots=True)
class FieldRule:
    rule_id: str
    canonical_field: str
    column: str
    headers: tuple[str, ...]
    converter: str
    required: bool = False
    unit: str = ""
    selector_strategy: str = "FIXED_COLUMN_HEADER"


@dataclass(frozen=True, slots=True)
class SheetRoleRule:
    role: str
    names: tuple[str, ...]
    required: bool = False
    header_row: int | None = None


@dataclass(frozen=True, slots=True)
class ImportProfile:
    profile_id: str
    profile_code: str
    profile_family: str
    revision: int
    name: str
    factories: tuple[str, ...]
    status: str
    sheet_roles: tuple[SheetRoleRule, ...]
    fields: tuple[FieldRule, ...]
    machine_adapter: str
    mold_adapter: str
    dynamic_shift_start: str
    dynamic_shift_end: str
    quantity_scope: str
    renderer_code: str
    document_kind: str = "PLANNED_SCHEDULE"
    source_namespace_id: str = ""
    title_aliases: tuple[str, ...] = ()
    anchor_aliases: tuple[str, ...] = ()
    termination_aliases: tuple[str, ...] = ()

    @property
    def current_plan_role(self) -> SheetRoleRule:
        if self.document_kind not in {"PLANNED_SCHEDULE", "SYSTEM_ROUND_TRIP"}:
            raise ValueError("只有计划表 Profile 才有 CURRENT_PLAN role")
        return next(item for item in self.sheet_roles if item.role == "CURRENT_PLAN")

    @property
    def primary_source_role(self) -> SheetRoleRule:
        expected = {
            "DEMAND_ORDER": "ORDER_SOURCE",
            "PLANNED_SCHEDULE": "CURRENT_PLAN",
            "SYSTEM_ROUND_TRIP": "CURRENT_PLAN",
        }.get(self.document_kind)
        if expected is None:
            return next(item for item in self.sheet_roles if item.required)
        return next(item for item in self.sheet_roles if item.role == expected)


CANONICAL_FIELD_CATALOG: dict[str, CanonicalField] = {
    item.name: item
    for item in (
        CanonicalField(
            "machine_code",
            "identifier",
            "BASELINE_DECISION",
            "machine assignment and grouping",
        ),
        CanonicalField(
            "item_no", "identifier", "SOURCE_FACT", "order identity and search"
        ),
        CanonicalField(
            "legacy_machine_class_text",
            "text",
            "SOURCE_FACT",
            "eligibility source evidence",
        ),
        CanonicalField(
            "mold_no", "identifier", "SOURCE_FACT", "mold identity and eligibility"
        ),
        CanonicalField(
            "product_name", "text", "SOURCE_FACT", "order display and search"
        ),
        CanonicalField(
            "order_no", "identifier", "SOURCE_FACT", "stable order identity"
        ),
        CanonicalField(
            "warehouse_text", "identifier", "SOURCE_FACT", "warehouse routing"
        ),
        CanonicalField(
            "set_quantity", "number", "SOURCE_FACT", "source quantity evidence"
        ),
        CanonicalField("order_quantity", "number", "SOURCE_FACT", "order demand"),
        CanonicalField(
            "completed_quantity", "number", "SOURCE_FACT", "takeover progress watermark"
        ),
        CanonicalField(
            "daily_target_quantity",
            "number",
            "SOURCE_FACT",
            "daily target with explicit unit",
        ),
        CanonicalField(
            "shift_target_quantity",
            "number",
            "SOURCE_FACT",
            "shift target with explicit unit",
        ),
        CanonicalField(
            "material_name", "text", "SOURCE_FACT", "eligibility and transition"
        ),
        CanonicalField("sprue_ratio", "percent", "SOURCE_FACT", "material source fact"),
        CanonicalField("color_name", "text", "SOURCE_FACT", "transition input"),
        CanonicalField(
            "color_powder_code", "identifier", "SOURCE_FACT", "color source fact"
        ),
        CanonicalField(
            "whole_shot_net_weight_g", "number", "SOURCE_FACT", "eligibility input"
        ),
        CanonicalField(
            "whole_shot_gross_weight_g",
            "number",
            "SOURCE_FACT",
            "source engineering fact",
        ),
        CanonicalField("order_date", "date", "SOURCE_FACT", "order chronology"),
        CanonicalField("delivery_start_date", "date", "SOURCE_FACT", "delivery window"),
        CanonicalField(
            "delivery_due_date", "date", "SOURCE_FACT", "delivery constraint"
        ),
        CanonicalField(
            "planned_start", "datetime", "BASELINE_DECISION", "takeover baseline window"
        ),
        CanonicalField(
            "planned_finish",
            "datetime",
            "BASELINE_DECISION",
            "takeover baseline window",
        ),
        CanonicalField(
            "requires_spray_paint", "text", "SOURCE_FACT", "process requirement"
        ),
        CanonicalField("remark", "text", "SOURCE_FACT", "operator note"),
        CanonicalField("required_arm_type", "text", "SOURCE_FACT", "eligibility input"),
        CanonicalField(
            "required_fixture_type", "text", "SOURCE_FACT", "eligibility input"
        ),
        CanonicalField(
            "automation_mode", "text", "LEGACY_DISPLAY", "source compatible display"
        ),
        CanonicalField(
            "legacy_marker", "text", "LEGACY_DISPLAY", "source status evidence"
        ),
        CanonicalField(
            "material_weight_kg",
            "number",
            "LEGACY_DISPLAY",
            "source compatible display",
        ),
        CanonicalField(
            "unit_price", "number", "LEGACY_DISPLAY", "source compatible display"
        ),
        CanonicalField(
            "outsource_price", "number", "LEGACY_DISPLAY", "source compatible display"
        ),
        CanonicalField(
            "price_ratio", "percent", "LEGACY_DISPLAY", "source compatible display"
        ),
        CanonicalField(
            "ship_date", "date", "LEGACY_DISPLAY", "source compatible display"
        ),
        CanonicalField(
            "legacy_mold_change", "text", "LEGACY_DISPLAY", "source compatible display"
        ),
        CanonicalField(
            "legacy_color_change", "text", "LEGACY_DISPLAY", "source compatible display"
        ),
        CanonicalField(
            "legacy_setup", "text", "LEGACY_DISPLAY", "source compatible display"
        ),
        CanonicalField(
            "legacy_downtime", "text", "LEGACY_DISPLAY", "source compatible display"
        ),
        CanonicalField(
            "source_outstanding_quantity", "number", "SYSTEM_DERIVED", "comparison only"
        ),
        CanonicalField(
            "source_plan_month", "text", "SYSTEM_DERIVED", "comparison only"
        ),
        CanonicalField(
            "source_delivery_slack", "number", "SYSTEM_DERIVED", "comparison only"
        ),
        CanonicalField(
            "source_production_days", "number", "SYSTEM_DERIVED", "comparison only"
        ),
        CanonicalField(
            "source_warehouse_date", "date", "SYSTEM_DERIVED", "comparison only"
        ),
        CanonicalField(
            "source_machine_finish", "text", "SYSTEM_DERIVED", "comparison only"
        ),
        CanonicalField(
            "customer_name", "text", "SOURCE_FACT", "customer identity evidence"
        ),
        CanonicalField(
            "source_document_no",
            "identifier",
            "SOURCE_FACT",
            "source document identity evidence",
        ),
        CanonicalField(
            "source_mold_no",
            "identifier",
            "SOURCE_FACT",
            "namespaced shared mold matching evidence",
        ),
        CanonicalField(
            "product_group_no",
            "identifier",
            "SOURCE_FACT",
            "source product grouping evidence",
        ),
        CanonicalField(
            "required_shots", "number", "SOURCE_FACT", "required shots evidence"
        ),
        CanonicalField(
            "source_daily_capacity",
            "number",
            "SOURCE_FACT",
            "source capacity candidate evidence",
        ),
        CanonicalField(
            "total_gross_weight",
            "number",
            "SOURCE_FACT",
            "source material calculation evidence",
        ),
        CanonicalField(
            "total_net_weight",
            "number",
            "SOURCE_FACT",
            "source material calculation evidence",
        ),
        CanonicalField(
            "source_mold_return_due",
            "text",
            "SOURCE_FACT",
            "unconfirmed source timing evidence",
        ),
    )
}

ALLOWED_CONVERTERS = frozenset(
    {"trim", "identifier", "number", "date", "datetime", "percent", "text"}
)
ALLOWED_MACHINE_ADAPTERS = frozenset(
    {"huaxing_machine_v1", "huakang_b_machine_v1", "system_master_only"}
)
ALLOWED_MOLD_ADAPTERS = frozenset({"huaxing_mold_v1", "system_master_only"})
ALLOWED_RENDERERS = frozenset(
    {
        "huaxing_daily_plan_v1",
        "huakang_b_daily_plan_v1",
        "system_standard_v1",
        "demand_order_review_v1",
        "master_data_review_v1",
    }
)
ALLOWED_SHEET_ROLES = frozenset(
    {
        "CURRENT_PLAN",
        "COMPLETED_HISTORY",
        "MACHINE_COMPLETION",
        "OUTSOURCED_PLAN",
        "CANCELLED_ORDER_HISTORY",
        "SHIFT_HISTORY",
        "MACHINE_MASTER",
        "MOLD_MASTER",
        "ORDER_SOURCE",
        "ORDER_META",
        "MOLD_DEFINITION_SOURCE",
        "MOLD_OUTPUT_SOURCE",
        "FACTORY_CAPABILITY_SOURCE",
        "PRICE_RULE_SOURCE",
    }
)
ALLOWED_DOCUMENT_KINDS = frozenset(
    {"DEMAND_ORDER", "PLANNED_SCHEDULE", "SYSTEM_ROUND_TRIP", "MASTER_DATA"}
)
ALLOWED_SELECTOR_STRATEGIES = frozenset({"FIXED_COLUMN_HEADER", "HEADER_ALIAS"})


def normalize_header(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).strip().lower()
    text = text.replace("（", "(").replace("）", ")")
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[,:;，：；。·_\-]", "", text)
    text = re.sub(r"\((?:kg|g|mm|cm|a|t|kw|hp|套|个|pcs?)\)$", "", text)
    return text


def _field(
    profile: str,
    canonical: str,
    column: str,
    headers: tuple[str, ...],
    converter: str,
    *,
    required: bool = False,
    unit: str = "",
    selector_strategy: str = "FIXED_COLUMN_HEADER",
) -> FieldRule:
    if canonical not in CANONICAL_FIELD_CATALOG:
        raise RuntimeError(f"unknown canonical field: {canonical}")
    if converter not in ALLOWED_CONVERTERS:
        raise RuntimeError(f"unsafe profile converter: {converter}")
    return FieldRule(
        rule_id=f"{profile}:{canonical}:r1",
        canonical_field=canonical,
        column=column,
        headers=headers,
        converter=converter,
        required=required,
        unit=unit,
        selector_strategy=selector_strategy,
    )


def _huaxing_fields() -> tuple[FieldRule, ...]:
    p = "huaxing_daily_plan_v1"
    return (
        _field(p, "machine_code", "B", ("机号", "机位"), "identifier", required=True),
        _field(p, "automation_mode", "D", ("是否全自动", "自动化"), "text"),
        _field(p, "legacy_marker", "E", ("备注", "标记", "旧标记"), "text"),
        _field(p, "legacy_machine_class_text", "F", ("机型", "安机"), "text"),
        _field(p, "mold_no", "G", ("工模", "模号"), "identifier", required=True),
        _field(p, "product_name", "H", ("名称", "产品名称"), "text", required=True),
        _field(p, "order_no", "I", ("单号", "订单号"), "identifier", required=True),
        _field(p, "item_no", "J", ("货号",), "identifier"),
        _field(p, "set_quantity", "K", ("数量(套)", "数量", "套数"), "number"),
        _field(
            p, "order_quantity", "L", ("订单数", "订单数量"), "number", required=True
        ),
        _field(
            p, "completed_quantity", "M", ("已啤数", "完成数"), "number", required=True
        ),
        _field(p, "source_outstanding_quantity", "N", ("欠数",), "number"),
        _field(
            p,
            "shift_target_quantity",
            "O",
            ("计划目标", "每班目标"),
            "number",
            unit="pieces/shift",
        ),
        _field(p, "sprue_ratio", "P", ("水口比例",), "percent"),
        _field(p, "color_name", "Q", ("颜色",), "text"),
        _field(p, "color_powder_code", "R", ("色粉",), "identifier"),
        _field(p, "material_name", "S", ("用料", "材料"), "text"),
        _field(p, "whole_shot_net_weight_g", "T", ("净重",), "number", unit="g"),
        _field(p, "whole_shot_gross_weight_g", "U", ("毛重",), "number", unit="g"),
        _field(
            p, "material_weight_kg", "V", ("用料重(kg)", "用料重"), "number", unit="kg"
        ),
        _field(p, "unit_price", "W", ("单价/啤", "单价"), "number"),
        _field(p, "outsource_price", "X", ("外发单价",), "number"),
        _field(p, "price_ratio", "Y", ("比例",), "percent"),
        _field(p, "order_date", "Z", ("下单期", "下单日期"), "date"),
        _field(p, "delivery_start_date", "AA", ("开始交货期",), "date"),
        _field(p, "delivery_due_date", "AB", ("交货完成期", "交货期"), "date"),
        _field(p, "legacy_mold_change", "AC", ("转模参考时间",), "text"),
        _field(p, "legacy_color_change", "AD", ("转色参考时间",), "text"),
        _field(p, "legacy_setup", "AE", ("转模/色时间",), "text"),
        _field(p, "legacy_downtime", "AF", ("机/模故时间",), "text"),
        _field(p, "planned_start", "AG", ("计划生产期", "计划啤货期"), "datetime"),
        _field(p, "planned_finish", "AH", ("计划完成期",), "datetime"),
        _field(p, "source_plan_month", "AI", ("计划完成月",), "text"),
        _field(p, "source_warehouse_date", "AJ", ("入库期",), "date"),
        _field(p, "source_delivery_slack", "AK", ("交期差",), "number"),
        _field(p, "requires_spray_paint", "AL", ("是否喷油",), "text"),
        _field(p, "source_production_days", "AM", ("啤货天数",), "number"),
        _field(p, "warehouse_text", "AR", ("仓库",), "identifier"),
        _field(p, "remark", "AS", ("备注",), "text"),
        _field(p, "ship_date", "AT", ("走货期",), "date"),
        _field(p, "required_arm_type", "AU", ("单双臂",), "text"),
        _field(p, "required_fixture_type", "AV", ("夹具", "气剪"), "text"),
    )


def _huakang_b_fields() -> tuple[FieldRule, ...]:
    p = "huakang_b_daily_plan_v1"
    return (
        _field(p, "machine_code", "B", ("机位",), "identifier", required=True),
        _field(p, "source_machine_finish", "C", ("计划啤完机台",), "text"),
        _field(p, "automation_mode", "D", ("备注", "是否全自动"), "text"),
        _field(p, "item_no", "E", ("货号",), "identifier"),
        _field(p, "legacy_machine_class_text", "F", ("安机",), "text"),
        _field(p, "mold_no", "G", ("工模", "模号"), "identifier", required=True),
        _field(p, "product_name", "H", ("名称",), "text", required=True),
        _field(p, "order_no", "I", ("单号", "订单号"), "identifier", required=True),
        _field(p, "warehouse_text", "J", ("仓库",), "identifier"),
        _field(p, "set_quantity", "K", ("套数",), "number"),
        _field(p, "order_quantity", "L", ("订单数",), "number", required=True),
        _field(p, "completed_quantity", "M", ("已啤数",), "number", required=True),
        _field(p, "source_outstanding_quantity", "N", ("欠数",), "number"),
        _field(
            p,
            "daily_target_quantity",
            "O",
            ("计划日目标",),
            "number",
            unit="pieces/day",
        ),
        _field(p, "material_name", "P", ("用料",), "text"),
        _field(p, "sprue_ratio", "Q", ("水口比例",), "percent"),
        _field(p, "color_name", "R", ("颜色",), "text"),
        _field(p, "color_powder_code", "S", ("色粉",), "identifier"),
        _field(p, "whole_shot_net_weight_g", "T", ("净重",), "number", unit="g"),
        _field(p, "whole_shot_gross_weight_g", "U", ("毛重",), "number", unit="g"),
        _field(p, "material_weight_kg", "V", ("用料重",), "number", unit="kg"),
        _field(p, "unit_price", "W", ("单价/啤",), "number"),
        _field(p, "order_date", "X", ("下单期",), "date"),
        _field(p, "delivery_start_date", "Y", ("开始交货期",), "date"),
        _field(p, "delivery_due_date", "Z", ("交货完成期",), "date"),
        _field(p, "legacy_mold_change", "AA", ("转模参考时间",), "text"),
        _field(p, "legacy_color_change", "AB", ("转色参考时间",), "text"),
        _field(p, "legacy_setup", "AC", ("转模/色时间",), "text"),
        _field(p, "legacy_downtime", "AD", ("机/模故时间",), "text"),
        _field(p, "planned_start", "AE", ("计划啤货期", "计划生产期"), "datetime"),
        _field(p, "planned_finish", "AF", ("计划完成期",), "datetime"),
        _field(p, "source_plan_month", "AG", ("计划完成月",), "text"),
        _field(p, "source_warehouse_date", "AH", ("入库期",), "date"),
        _field(p, "source_delivery_slack", "AI", ("交期差",), "number"),
        _field(p, "source_production_days", "AJ", ("啤货天数",), "number"),
        _field(p, "requires_spray_paint", "AK", ("是否喷油",), "text"),
        _field(
            p,
            "shift_target_quantity",
            "AN",
            ("每班计划啤数",),
            "number",
            unit="pieces/shift",
        ),
        _field(p, "remark", "AT", ("备注",), "text"),
        _field(p, "required_arm_type", "AU", ("单双臂",), "text"),
        _field(p, "required_fixture_type", "AV", ("气剪", "夹具"), "text"),
    )


def _system_standard_fields() -> tuple[FieldRule, ...]:
    p = "system_standard_v1"
    return (
        _field(p, "machine_code", "A", ("机台编码",), "identifier", required=True),
        _field(p, "mold_no", "B", ("模具编号",), "identifier", required=True),
        _field(p, "product_name", "C", ("产品名称",), "text", required=True),
        _field(p, "order_no", "D", ("订单号",), "identifier", required=True),
        _field(p, "item_no", "E", ("货号",), "identifier"),
        _field(p, "order_quantity", "F", ("订单数量",), "number", required=True),
        _field(
            p, "completed_quantity", "G", ("累计完成数量",), "number", required=True
        ),
        _field(
            p,
            "shift_target_quantity",
            "H",
            ("班次目标数量",),
            "number",
            unit="pieces/shift",
        ),
        _field(p, "delivery_due_date", "I", ("交货完成期",), "date"),
        _field(p, "planned_start", "J", ("计划开始",), "datetime"),
        _field(p, "planned_finish", "K", ("计划完成",), "datetime"),
        _field(p, "material_name", "L", ("材料",), "text"),
        _field(p, "color_name", "M", ("颜色",), "text"),
        _field(p, "warehouse_text", "N", ("仓库",), "identifier"),
        _field(p, "remark", "O", ("备注",), "text"),
        _field(p, "required_arm_type", "P", ("机械手",), "text"),
        _field(p, "required_fixture_type", "Q", ("夹具",), "text"),
    )


def _demand_order_fields() -> tuple[FieldRule, ...]:
    p = "demand_order_shared_v1"

    def demand_field(
        canonical: str,
        fallback_column: str,
        aliases: tuple[str, ...],
        converter: str,
        *,
        required: bool = False,
        unit: str = "",
    ) -> FieldRule:
        return _field(
            p,
            canonical,
            fallback_column,
            aliases,
            converter,
            required=required,
            unit=unit,
            selector_strategy="HEADER_ALIAS",
        )

    return (
        demand_field("product_group_no", "A", ("款号", "产品款号"), "identifier"),
        demand_field(
            "source_mold_no",
            "B",
            ("模具编号", "工模编号", "工模编码", "模号"),
            "identifier",
            required=True,
        ),
        demand_field(
            "product_name",
            "C",
            ("工模名称", "产品名称", "名称"),
            "text",
            required=True,
        ),
        demand_field(
            "order_quantity", "D", ("数量", "订单数量"), "number", required=True
        ),
        demand_field("set_quantity", "E", ("总套数", "套数"), "number"),
        demand_field("required_shots", "F", ("啤数", "总啤数"), "number"),
        demand_field("color_name", "G", ("颜色",), "text"),
        demand_field("color_powder_code", "H", ("色粉号", "色粉"), "identifier"),
        demand_field("material_name", "I", ("用料名称", "用料", "材料"), "text"),
        demand_field("source_daily_capacity", "J", ("模具日产量", "日产量"), "number"),
        demand_field(
            "whole_shot_gross_weight_g",
            "K",
            ("整啤毛重", "毛重"),
            "number",
            unit="g",
        ),
        demand_field(
            "whole_shot_net_weight_g",
            "L",
            ("整啤净重", "净重"),
            "number",
            unit="g",
        ),
        demand_field("total_gross_weight", "M", ("总毛重",), "number"),
        demand_field("total_net_weight", "N", ("总净重",), "number"),
        demand_field("sprue_ratio", "O", ("水口比例",), "percent"),
        demand_field("source_mold_return_due", "P", ("啤机复期", "复期"), "text"),
        demand_field("remark", "Q", ("备注", "说明"), "text"),
    )


BUILTIN_IMPORT_PROFILES: tuple[ImportProfile, ...] = (
    ImportProfile(
        profile_id="isprofile-huaxing-daily-v1",
        profile_code="huaxing_daily_plan_v1",
        profile_family="huaxing_daily_plan",
        revision=1,
        name="华兴啤机日排表 v1",
        factories=("huaxing",),
        status="ACTIVE",
        sheet_roles=(
            SheetRoleRule("CURRENT_PLAN", ("计划表",), True, 3),
            SheetRoleRule(
                "COMPLETED_HISTORY", ("已啤记录2026", "已啤记录2025", "已啤记录2024")
            ),
            SheetRoleRule("MACHINE_COMPLETION", ("机台完成时间",)),
            SheetRoleRule("SHIFT_HISTORY", ("每班啤数记录",)),
            SheetRoleRule("MOLD_MASTER", ("机安",), False, 1),
            SheetRoleRule("MACHINE_MASTER", ("华兴机器设备",), False, 2),
        ),
        fields=_huaxing_fields(),
        machine_adapter="huaxing_machine_v1",
        mold_adapter="huaxing_mold_v1",
        dynamic_shift_start="BA",
        dynamic_shift_end="ZZ",
        quantity_scope="ORDER_CUMULATIVE",
        renderer_code="huaxing_daily_plan_v1",
    ),
    ImportProfile(
        profile_id="isprofile-huakang-b-daily-v1",
        profile_code="huakang_b_daily_plan_v1",
        profile_family="huakang_b_daily_plan",
        revision=1,
        name="华康 B 啤机日排表 v1",
        factories=("huakang-b",),
        status="ACTIVE",
        sheet_roles=(
            SheetRoleRule("CURRENT_PLAN", ("排期表",), True, 3),
            SheetRoleRule("COMPLETED_HISTORY", ("已啤完",)),
            SheetRoleRule("MACHINE_COMPLETION", ("机台完成时间",)),
            SheetRoleRule("OUTSOURCED_PLAN", ("外发2",)),
            SheetRoleRule("MACHINE_MASTER", ("厂区现有啤机",), False, 3),
            SheetRoleRule("CANCELLED_ORDER_HISTORY", ("取消订单",)),
            SheetRoleRule("SHIFT_HISTORY", ("每班啤数记录",)),
        ),
        fields=_huakang_b_fields(),
        machine_adapter="huakang_b_machine_v1",
        mold_adapter="system_master_only",
        dynamic_shift_start="AW",
        dynamic_shift_end="DF",
        quantity_scope="ORDER_CUMULATIVE",
        renderer_code="huakang_b_daily_plan_v1",
    ),
    ImportProfile(
        profile_id="isprofile-demand-order-shared-v1",
        profile_code="demand_order_shared_v1",
        profile_family="demand_order_shared",
        revision=1,
        name="啤机部生产啤货表（公共需求单）v1",
        factories=(
            "huaxing",
            "huakang-a",
            "huakang-b",
            "huakang-c",
            "huakang-d",
            "huadeng",
        ),
        status="ACTIVE",
        sheet_roles=(
            SheetRoleRule("ORDER_SOURCE", ("啤货表", "下单表", "订单表"), True),
            SheetRoleRule("ORDER_META", ("啤货表", "下单表", "订单表")),
        ),
        fields=_demand_order_fields(),
        machine_adapter="system_master_only",
        mold_adapter="system_master_only",
        dynamic_shift_start="A",
        dynamic_shift_end="A",
        quantity_scope="ORDER_CUMULATIVE",
        renderer_code="demand_order_review_v1",
        document_kind="DEMAND_ORDER",
        source_namespace_id="demand-order:company",
        title_aliases=("啤机部生产啤货表",),
        anchor_aliases=("公司名称", "交货日期", "单号"),
        termination_aliases=("备注", "下单日期", "操作员"),
    ),
    ImportProfile(
        profile_id="isprofile-master-data-shared-v1",
        profile_code="master_data_shared_v1",
        profile_family="master_data_shared",
        revision=1,
        name="共享模具与价格主数据证据 v1",
        factories=(
            "huaxing",
            "huakang-a",
            "huakang-b",
            "huakang-c",
            "huakang-d",
            "huadeng",
        ),
        status="ACTIVE",
        sheet_roles=(
            SheetRoleRule(
                "MOLD_DEFINITION_SOURCE",
                ("机安", "模具资料", "模具主数据"),
            ),
            SheetRoleRule("PRICE_RULE_SOURCE", ("单价", "价格", "价格规则")),
        ),
        fields=(),
        machine_adapter="system_master_only",
        mold_adapter="system_master_only",
        dynamic_shift_start="A",
        dynamic_shift_end="A",
        quantity_scope="ORDER_CUMULATIVE",
        renderer_code="master_data_review_v1",
        document_kind="MASTER_DATA",
        source_namespace_id="master-data:company",
    ),
)

SYSTEM_STANDARD_EXPORT_PROFILE = ImportProfile(
    profile_id="isprofile-system-standard-v1",
    profile_code="system_standard_v1",
    profile_family="system_standard",
    revision=1,
    name="系统标准注塑排产 v1",
    factories=(
        "huaxing",
        "huakang-a",
        "huakang-b",
        "huakang-c",
        "huakang-d",
        "huadeng",
    ),
    status="ACTIVE",
    sheet_roles=(SheetRoleRule("CURRENT_PLAN", ("计划表",), True, 1),),
    fields=_system_standard_fields(),
    machine_adapter="system_master_only",
    mold_adapter="system_master_only",
    dynamic_shift_start="A",
    dynamic_shift_end="A",
    quantity_scope="ORDER_CUMULATIVE",
    renderer_code="system_standard_v1",
)


def profile_config(profile: ImportProfile) -> dict[str, Any]:
    return {
        "profile_id": profile.profile_id,
        "profile_code": profile.profile_code,
        "profile_family": profile.profile_family,
        "revision": profile.revision,
        "name": profile.name,
        "factories": list(profile.factories),
        "status": profile.status,
        "sheet_roles": [
            {
                "role": item.role,
                "names": list(item.names),
                "required": item.required,
                "header_row": item.header_row,
            }
            for item in profile.sheet_roles
        ],
        "fields": [
            {
                "rule_id": item.rule_id,
                "canonical_field": item.canonical_field,
                "column": item.column,
                "headers": list(item.headers),
                "converter": item.converter,
                "required": item.required,
                "unit": item.unit,
                "authority": CANONICAL_FIELD_CATALOG[item.canonical_field].authority,
                **(
                    {"selector_strategy": item.selector_strategy}
                    if item.selector_strategy != "FIXED_COLUMN_HEADER"
                    else {}
                ),
            }
            for item in profile.fields
        ],
        "machine_adapter": profile.machine_adapter,
        "mold_adapter": profile.mold_adapter,
        "dynamic_shift_start": profile.dynamic_shift_start,
        "dynamic_shift_end": profile.dynamic_shift_end,
        "quantity_scope": profile.quantity_scope,
        "renderer_code": profile.renderer_code,
        **(
            {
                "document_kind": profile.document_kind,
                "source_namespace_id": profile.source_namespace_id,
                "recognition": {
                    "title_aliases": list(profile.title_aliases),
                    "anchor_aliases": list(profile.anchor_aliases),
                    "termination_aliases": list(profile.termination_aliases),
                },
            }
            if profile.document_kind != "PLANNED_SCHEDULE"
            else {}
        ),
    }


def profile_config_json(profile: ImportProfile) -> str:
    return json.dumps(
        profile_config(profile),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def profile_definition_digest(profile: ImportProfile) -> str:
    definition = profile_config(profile)
    # Lifecycle status and factory bindings are governed in separate columns/
    # tables. They may change without mutating the executable mapping revision.
    definition.pop("status", None)
    definition.pop("factories", None)
    payload = json.dumps(
        definition, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def profile_template_signature(profile: ImportProfile) -> str:
    stable_structure = {
        "profile_family": profile.profile_family,
        "document_kind": profile.document_kind,
        "sheet_roles": [
            {
                "role": item.role,
                "names": list(item.names),
                "required": item.required,
                "header_row": item.header_row,
            }
            for item in profile.sheet_roles
        ],
        "fields": [
            {
                "canonical_field": item.canonical_field,
                "column": item.column,
                "headers": [normalize_header(value) for value in item.headers],
                "converter": item.converter,
                "selector_strategy": item.selector_strategy,
            }
            for item in profile.fields
        ],
    }
    payload = json.dumps(
        stable_structure, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def profile_header_fingerprint(profile: ImportProfile) -> str:
    headers = [
        (
            item.column,
            item.canonical_field,
            tuple(normalize_header(value) for value in item.headers),
        )
        for item in profile.fields
    ]
    payload = json.dumps(headers, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def profile_from_config(config: dict[str, Any]) -> ImportProfile:
    required_keys = {
        "profile_id",
        "profile_code",
        "profile_family",
        "revision",
        "name",
        "factories",
        "status",
        "sheet_roles",
        "fields",
        "machine_adapter",
        "mold_adapter",
        "dynamic_shift_start",
        "dynamic_shift_end",
        "quantity_scope",
        "renderer_code",
    }
    missing = sorted(required_keys - set(config))
    if missing:
        raise ValueError(f"Profile 缺少字段: {', '.join(missing)}")
    status = str(config["status"])
    if status not in {"PROFILE_DRAFT", "ACTIVE", "RETIRED"}:
        raise ValueError("Profile status 无效")
    fields: list[FieldRule] = []
    seen_fields: set[str] = set()
    for item in config["fields"]:
        canonical = str(item["canonical_field"])
        converter = str(item["converter"])
        if canonical not in CANONICAL_FIELD_CATALOG:
            raise ValueError(f"Profile 引用了未知规范字段: {canonical}")
        if canonical in seen_fields:
            raise ValueError(f"Profile 重复映射规范字段: {canonical}")
        if converter not in ALLOWED_CONVERTERS:
            raise ValueError(f"Profile 使用了不安全转换器: {converter}")
        seen_fields.add(canonical)
        fields.append(
            FieldRule(
                rule_id=str(item["rule_id"]),
                canonical_field=canonical,
                column=str(item["column"]).upper(),
                headers=tuple(str(value) for value in item["headers"]),
                converter=converter,
                required=bool(item.get("required", False)),
                unit=str(item.get("unit", "")),
                selector_strategy=str(
                    item.get("selector_strategy", "FIXED_COLUMN_HEADER")
                ),
            )
        )
    roles = tuple(
        SheetRoleRule(
            role=str(item["role"]),
            names=tuple(str(value) for value in item["names"]),
            required=bool(item.get("required", False)),
            header_row=int(item["header_row"]) if item.get("header_row") else None,
        )
        for item in config["sheet_roles"]
    )
    document_kind = str(config.get("document_kind", "PLANNED_SCHEDULE"))
    if document_kind not in ALLOWED_DOCUMENT_KINDS:
        raise ValueError("Profile document_kind 无效")
    expected_role = {
        "PLANNED_SCHEDULE": "CURRENT_PLAN",
        "SYSTEM_ROUND_TRIP": "CURRENT_PLAN",
        "DEMAND_ORDER": "ORDER_SOURCE",
    }.get(document_kind)
    if expected_role and sum(item.role == expected_role for item in roles) != 1:
        raise ValueError(
            f"{document_kind} Profile 必须且只能声明一个 {expected_role} role"
        )
    unknown_roles = sorted({item.role for item in roles} - ALLOWED_SHEET_ROLES)
    if unknown_roles:
        raise ValueError(f"Profile 引用了未知 Sheet role: {', '.join(unknown_roles)}")
    profile = ImportProfile(
        profile_id=str(config["profile_id"]),
        profile_code=str(config["profile_code"]),
        profile_family=str(config["profile_family"]),
        revision=int(config["revision"]),
        name=str(config["name"]),
        factories=tuple(str(value) for value in config["factories"]),
        status=status,
        sheet_roles=roles,
        fields=tuple(fields),
        machine_adapter=str(config["machine_adapter"]),
        mold_adapter=str(config["mold_adapter"]),
        dynamic_shift_start=str(config["dynamic_shift_start"]).upper(),
        dynamic_shift_end=str(config["dynamic_shift_end"]).upper(),
        quantity_scope=str(config["quantity_scope"]),
        renderer_code=str(config["renderer_code"]),
        document_kind=document_kind,
        source_namespace_id=str(config.get("source_namespace_id", "")),
        title_aliases=tuple(
            str(value)
            for value in config.get("recognition", {}).get("title_aliases", [])
        ),
        anchor_aliases=tuple(
            str(value)
            for value in config.get("recognition", {}).get("anchor_aliases", [])
        ),
        termination_aliases=tuple(
            str(value)
            for value in config.get("recognition", {}).get("termination_aliases", [])
        ),
    )
    if profile.quantity_scope not in {"ORDER_CUMULATIVE", "SPLIT_CUMULATIVE"}:
        raise ValueError("Profile quantity_scope 无效")
    if profile.machine_adapter not in ALLOWED_MACHINE_ADAPTERS:
        raise ValueError("Profile machine_adapter 无效")
    if profile.mold_adapter not in ALLOWED_MOLD_ADAPTERS:
        raise ValueError("Profile mold_adapter 无效")
    if profile.renderer_code not in ALLOWED_RENDERERS:
        raise ValueError("Profile renderer_code 无效")
    invalid_selectors = sorted(
        {
            item.selector_strategy
            for item in profile.fields
            if item.selector_strategy not in ALLOWED_SELECTOR_STRATEGIES
        }
    )
    if invalid_selectors:
        raise ValueError(
            f"Profile selector strategy 无效: {', '.join(invalid_selectors)}"
        )
    column_pattern = re.compile(r"^[A-Z]{1,3}$")
    if not column_pattern.fullmatch(
        profile.dynamic_shift_start
    ) or not column_pattern.fullmatch(profile.dynamic_shift_end):
        raise ValueError("Profile 动态班次列范围无效")
    if profile.revision < 1:
        raise ValueError("Profile revision 必须大于 0")
    return profile


def profiles_for_factory(
    factory_id: str,
    document_kind: str = "PLANNED_SCHEDULE",
) -> tuple[ImportProfile, ...]:
    return tuple(
        item
        for item in BUILTIN_IMPORT_PROFILES
        if factory_id in item.factories and item.document_kind == document_kind
    )


def get_builtin_profile(
    profile_id: str, revision: int | None = None
) -> ImportProfile | None:
    return next(
        (
            item
            for item in BUILTIN_IMPORT_PROFILES
            if item.profile_id == profile_id
            and (revision is None or item.revision == revision)
        ),
        None,
    )
