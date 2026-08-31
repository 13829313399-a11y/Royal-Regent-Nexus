from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ImportProfile:
    code: str
    document_type: str
    title_signals: tuple[str, ...]
    required_headers: tuple[str, ...]


HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "machine_code": ("机位", "机号"),
    "required_machine_a_label": ("安机", "机安", "机器安数"),
    "product_code": ("货号", "款号"),
    "mold_code": ("工模", "模具编号"),
    "product_name": ("名称", "工模名称"),
    "order_no": ("单号",),
    "warehouse": ("仓库",),
    "quantity_sets": ("套数", "数量(套)", "数量（套）", "数量"),
    "total_sets": ("总套数",),
    "order_shots": ("订单数", "啤数"),
    "qualified_shots": ("已啤数",),
    "remaining_shots": ("欠数",),
    "daily_target": ("计划日目标", "计划目标", "模具日产量"),
    "water_ratio": ("水口比例",),
    "color": ("颜色",),
    "pigment_code": ("色粉", "色粉号"),
    "material_name": ("用料", "用料名称"),
    "net_weight_g": ("净重", "整啤净重"),
    "gross_weight_g": ("毛重", "总毛重", "整啤毛重"),
    "material_weight_kg": ("用料重", "用料重（KG）", "用料重(KG)"),
    "order_date": ("下单期", "下单日期"),
    "delivery_start_date": ("开始交货期",),
    "delivery_due_date": ("交货完成期", "交货日期", "交货"),
    "remark": ("备注",),
}


IMPORT_PROFILES: dict[str, ImportProfile] = {
    "WAREHOUSE_ORDER_FLAT_V1": ImportProfile(
        code="WAREHOUSE_ORDER_FLAT_V1",
        document_type="FLAT_ORDER",
        title_signals=(),
        required_headers=("款号", "模具编号", "工模名称", "单号"),
    ),
    "PRODUCTION_ORDER_FORM_V1": ImportProfile(
        code="PRODUCTION_ORDER_FORM_V1",
        document_type="ORDER_FORM",
        title_signals=("啤 机 部 生 产 啤 货 表", "啤机部生产啤货表"),
        required_headers=("款号", "模具编号", "工模名称"),
    ),
    "HK_B_PLAN_V1": ImportProfile(
        code="HK_B_PLAN_V1",
        document_type="PLAN_MIGRATION",
        title_signals=("河源华康B啤机生产日计划表",),
        required_headers=("工模", "名称", "单号", "货号"),
    ),
    "HUA_XING_PLAN_V1": ImportProfile(
        code="HUA_XING_PLAN_V1",
        document_type="PLAN_MIGRATION",
        title_signals=("河源华兴啤机生产日计划表",),
        required_headers=("工模", "名称", "单号", "货号"),
    ),
}


def canonical_header(value: object) -> str:
    normalized = re.sub(r"\s+", "", str(value or "")).replace("：", ":")
    for field_name, aliases in HEADER_ALIASES.items():
        if normalized in {re.sub(r"\s+", "", alias) for alias in aliases}:
            return field_name
    return ""
