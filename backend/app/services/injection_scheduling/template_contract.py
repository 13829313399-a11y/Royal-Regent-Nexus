from __future__ import annotations

from pathlib import Path

UNIFIED_IMPORT_PROFILE = "UNIFIED_PLAN_V2"
UNIFIED_TEMPLATE_VERSION = "2.0"
UNIFIED_TEMPLATE_TITLE = "Royal Regent Nexus · 统一注塑排产计划表"
UNIFIED_TEMPLATE_VERSION_MARKER = f"模板版本：{UNIFIED_TEMPLATE_VERSION}"
UNIFIED_PLAN_SHEET = "统一计划表"
UNIFIED_REQUIRED_SHEETS = frozenset({UNIFIED_PLAN_SHEET})
UNIFIED_PLAN_HEADERS = (
    "机号",
    "排产顺序",
    "状态",
    "锁定",
    "优先级",
    "模具安数",
    "工模",
    "名称",
    "单号",
    "货号",
    "数量(套)",
    "订单数",
    "已啤数",
    "欠数",
    "进度",
    "计划目标",
    "本班已啤",
    "水口比例",
    "颜色",
    "色粉",
    "颜色明度",
    "用料",
    "净重(g)",
    "毛重(g)",
    "用料重(KG)",
    "下单期",
    "开始交货期",
    "交货完成期",
    "转模参考(h)",
    "转色参考(h)",
    "转模/色时间(h)",
    "机/模故时间(h)",
    "计划生产期",
    "计划完成期",
    "计划完成月",
    "入库期",
    "交期差(天)",
    "啤货天数",
    "机台安数",
    "射胶量(g)",
    "仓库",
    "备注",
    "走货期",
    "单双臂",
    "夹具",
    "原料状态",
    "已配料重(KG)",
    "料欠(KG)",
    "更新人",
    "更新时间",
    "工厂ID",
    "排产行ID",
    "订单模具ID",
    "来源批次ID",
    "来源行号",
    "数据版本",
)

INJECTION_FACTORY_IDS = frozenset({"huakang-a", "huakang-b", "huadeng", "huaxing"})
FACTORY_NAMES = {
    "huakang-a": "华康 A 厂",
    "huakang-b": "华康 B 厂",
    "huadeng": "华登厂",
    "huaxing": "华兴厂",
}
SHARED_MOLD_SCOPE_ID = "company"
SHARED_MOLD_SCOPE_TYPE = "COMPANY_SHARED"

_RESOURCE_DIR = (
    Path(__file__).resolve().parents[2] / "resources" / "injection_scheduling"
)


def unified_template_path() -> Path:
    return _RESOURCE_DIR / f"unified-plan-v{UNIFIED_TEMPLATE_VERSION}.xlsx"


def unified_template_download_name() -> str:
    return f"统一注塑排产计划表模板_V{UNIFIED_TEMPLATE_VERSION}.xlsx"
