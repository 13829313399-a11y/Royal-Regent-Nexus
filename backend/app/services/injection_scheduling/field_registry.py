"""One public contract for editing, SQL queries, UI columns and XLSX."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FieldSpec:
    key: str
    label: str
    value_type: str = "text"
    editable: bool = True
    group: str = "process"
    legacy_column: str | None = None
    unit: str | None = None
    sortable: bool = True
    exportable: bool = True

    @property
    def filter_ops(self):
        common = ["eq", "ne", "in", "not_in", "is_empty", "not_empty"]
        if self.value_type in {"number", "integer", "datetime"}:
            return (
                common
                + ["gt", "gte", "lt", "lte", "between"]
                + (
                    ["today", "next_days", "overdue", "on_day"]
                    if self.value_type == "datetime"
                    else []
                )
            )
        return common + ["contains", "prefix"]

    def public(self):
        return {**asdict(self), "filter_ops": self.filter_ops}


# A:AX order is stable. Unexplained auxiliary fields remain evidence, not rules.
LEGACY_FIELDS = [
    ("machine_block_marker", "机位标记", "text", False, "source"),
    ("machine_code", "机号", "text", False, "schedule"),
    ("legacy_last_row_marker", "原末行标记", "text", False, "source"),
    ("automation_requirement", "自动化要求", "text", True, "process"),
    ("order_note", "订单备注", "text", True, "delivery"),
    ("required_machine_a", "模具机安 A", "number", True, "process"),
    ("mold_code", "模号", "text", True, "identity"),
    ("part_name", "名称", "text", True, "identity"),
    ("order_no", "单号", "text", True, "identity"),
    ("item_no", "货号", "text", True, "identity"),
    ("demand_sets", "需求套数", "number", True, "quantity"),
    ("planned_shots", "计划啤数", "number", True, "quantity"),
    ("completed_shots", "已啤数", "number", False, "quantity"),
    ("remaining_shots", "欠数", "number", False, "quantity"),
    ("target_shots_per_day", "计划日目标", "number", True, "process"),
    ("regrind_ratio_raw", "水口比例原值", "text", True, "process"),
    ("color_name", "颜色", "text", True, "process"),
    ("colorant_code", "色粉", "text", True, "process"),
    ("material_raw", "用料", "text", True, "process"),
    ("net_weight_g", "每啤净重 g", "number", True, "process"),
    ("gross_weight_g", "毛重 g", "number", True, "process"),
    ("remaining_material_kg", "剩余料重 kg", "number", False, "quantity"),
    ("price_per_shot", "单价/啤", "number", True, "process"),
    ("remaining_processing_amount", "剩余加工金额", "number", False, "quantity"),
    ("ratio_raw", "原比例（未解释）", "text", True, "source"),
    ("ordered_on", "下单期", "datetime", True, "delivery"),
    ("delivery_window_start", "开始交货期", "datetime", True, "delivery"),
    ("delivery_due_at", "交货完成期", "datetime", True, "delivery"),
    ("mold_change_minutes", "换模分钟", "number", False, "schedule"),
    ("color_change_minutes", "清洗换色分钟", "number", False, "schedule"),
    ("changeover_minutes", "总转换分钟", "number", False, "schedule"),
    ("legacy_weeknum_delta", "原周序号差（非检修）", "number", False, "source"),
    ("planned_start_at", "预计生产开始", "datetime", False, "schedule"),
    ("planned_end_at", "预计生产完成", "datetime", False, "schedule"),
    ("planned_completion_month", "计划完成月", "text", False, "schedule"),
    ("expected_stock_ready_at", "预计入库期", "datetime", False, "delivery"),
    ("delivery_slack_hours", "交期宽裕小时", "number", False, "delivery"),
    ("requires_painting", "是否喷油", "text", True, "process"),
    ("production_duration_hours", "纯生产小时", "number", False, "schedule"),
    ("shift_end_at", "本班结束", "datetime", False, "schedule"),
    ("remaining_shift_hours", "本班剩余小时", "number", False, "schedule"),
    ("expected_shift_shots", "本班预计啤数", "number", False, "schedule"),
    ("legacy_machine_type_aux", "原辅助机型", "text", False, "source"),
    ("warehouse_note", "仓库", "text", True, "delivery"),
    ("production_note", "工艺备注", "text", True, "process"),
    ("legacy_lookup_at_raw", "原 AT 查找值（未解释）", "text", False, "source"),
    ("manipulator_requirement", "机械手要求", "text", True, "process"),
    ("fixture_requirement", "夹具要求", "text", True, "process"),
    ("legacy_undated_day_qty", "原无日期白班", "number", False, "source"),
    ("legacy_undated_night_qty", "原无日期夜班", "number", False, "source"),
]


def column_name(n):
    result = ""
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


FIELDS = {
    key: FieldSpec(key, label, typ, editable, group, column_name(i))
    for i, (key, label, typ, editable, group) in enumerate(LEGACY_FIELDS, 1)
}
for key, label, typ, edit, group in [
    ("id", "需求 ID", "text", False, "identity"),
    ("dispatch_state", "需求状态", "text", True, "identity"),
    ("priority_level", "急单等级", "integer", True, "delivery"),
    ("color_depth_rank", "颜色深浅等级", "integer", True, "process"),
    ("resin", "树脂", "text", True, "process"),
    ("material_grade", "材料牌号", "text", True, "process"),
    ("target_basis_hours", "日目标折算小时", "number", True, "process"),
    ("downstream_lead_days", "下游准备天数", "number", True, "delivery"),
    ("earliest_available_at", "最早可生产时间", "datetime", True, "delivery"),
    ("pieces_per_set", "每套件数", "number", True, "quantity"),
    ("effective_outputs_per_shot", "有效每啤出件", "number", True, "quantity"),
    ("required_units", "需求良品件", "number", True, "quantity"),
    ("good_units", "累计良品件", "number", False, "quantity"),
    ("remaining_units", "欠良品件", "number", False, "quantity"),
    ("overproduced_shots", "超产啤数", "number", False, "quantity"),
    ("quantity_basis", "数量口径", "text", False, "quantity"),
    ("allocation_mode", "分配口径", "text", True, "quantity"),
    ("weight_basis", "重量口径", "text", True, "process"),
    ("allowance_rate", "材料附加系数", "number", True, "process"),
    ("adjustment_shots", "补数调整", "number", True, "quantity"),
    ("source_document", "来源文件", "text", False, "source"),
    ("source_row", "来源行", "integer", False, "source"),
    ("unplaced_reason", "未排原因", "text", False, "schedule"),
    ("requirements_snapshot", "本单适机限制", "json", True, "process"),
    ("output_configuration", "出件配置", "json", True, "process"),
    ("co_output_group", "同啤产物组", "text", True, "process"),
]:
    FIELDS[key] = FieldSpec(key, label, typ, edit, group)

FACTORIES = {
    "huaxing": "华兴",
    "huadeng": "华登",
    "huakang-a": "华康 A",
    "huakang-b": "华康 B",
}
