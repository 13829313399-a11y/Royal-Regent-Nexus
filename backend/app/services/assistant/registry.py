"""Explicit coverage and dispatch. A help page is not a business connector."""
from dataclasses import dataclass
from .errors import AssistantError


@dataclass(frozen=True)
class Connector:
    module_id: str
    label: str
    coverage_state: str
    tool_name: str | None = None
    route_name: str | None = None
    resource_type: str | None = None
    description: str = ""
    authorize_symbol: str | None = None
    domain_reader: str | None = None
    blocker: str | None = None
    extra_resource_types: tuple[str, ...] = ()
    coverage_description: str = ""

    @property
    def callable(self):
        return self.coverage_state in {"implemented_unverified", "connected"}


CONNECTORS = (
    Connector("work-center", "我的工作", "implemented_unverified", "get_my_work", "notification-center", "entry",
              "读取本人可见事项；统计区分全授权与选中厂区，未覆盖领域不推断为零",
              "assistant.business.authorize + work_center.registry.scoped", "work_center.service.snapshot/detail",
              coverage_description="查看本人可见事项，区分全部授权范围与选中厂区；未覆盖的业务不会按零统计。"),
    Connector("injection-scheduling", "注塑排期", "implemented_unverified", "get_injection_overview", "injection-scheduling", "demand",
              "读取四厂注塑排期；held非缺料，剩余用料非库存缺口，排期风险非实际延期",
              "assistant.business.authorize + business_authz.has_permission_for_departments", "injection_scheduling.queries.query_conditions/summary",
              coverage_description="查看注塑需求与排期。剩余用料不等于库存缺口，排期风险不等于实际延期。"),
    Connector("three-d-printing", "3D 打印", "implemented_unverified", "get_printer_status", "three-d-printing-management", "printer",
              "读取华康A机台快照与新鲜度，不控制设备，过期遥测不能断言物理停机",
              "assistant.business.authorize + auth.has_permission_in_scope", "three_d_printing.printer_status_snapshot + three_d_workspace.printer_detail",
              coverage_description="查看华康A机台状态和采集时间。过期状态不能证明设备停机；不控制设备。"),
    Connector("customer-orders", "客户订单", "implemented_unverified", "list_customer_orders", "customer-order-center", "order",
              "按明确厂区查询订单台账、筛选汇总或resource_id详情；数量是原订单单位，未知不当零；可用cursor续页，不含生产/库存推断",
              "assistant.orders.authorize + business_authz.has_permission_for_departments", "customer_order_queries.statement/progress/read_slice + customer_order_ledger.detail",
              coverage_description="查看当前厂区订单台账、筛选汇总与详情，保留原订单单位；不推断生产进度或库存。"),
    Connector("carton-procurement", "纸箱采购", "implemented_unverified", "get_carton_overview", "carton-procurement", "order",
              "读取纸品合并订单台账或库存汇总；订单默认本人负责，ALL沿原权限；数量分原单位，采购未到、历史结存、当前仓位与未知可用量分开；库存resource_id须使用view=inventory并保留期间",
              "assistant.cartons.authorize + native special/selected/responsibility authority",
              "carton_order_queries.ledger + carton_unified_order_actions.selected + carton_inventory_report.inventory_report",
              extra_resource_types=("inventory",),
              coverage_description="按原权限查看本人负责或全部可见的纸品订单；库存另行核对读取权限。采购未到、历史结存与当前仓位分开统计。"),
    Connector("uv-operations", "UV 生产", "implemented_unverified", "get_uv_operations_snapshot", "uv-planning", "task",
              "读取华康A原UV任务、active批次与完整范围数量。合格按原批次good，返工/多道次不重复，剩余不是逾期；不含设备控制、费用工资或结算，未接入项明确未知",
              "uv_operations.authz.authorize/ready", "uv_operations.production.task_detail + common.query",
              coverage_description="查看华康A的UV任务与批次数量，返工和多道次不重复累计；不含设备控制、工资费用或结算。"),
    Connector("spray-production", "喷油生产", "implemented_unverified", "get_spray_operations_snapshot", "spray-demands", "demand",
              "四厂喷油只读：view=demands查需求、当前实体库存与累计交接；view=tasks查工序任务及已确认日报，task_scope=active仅待开/执行/暂停。合格在库、工序量、返工与报废分开，金额和缺料未知；可按resource_id查原记录",
              "spray_ops.authz.authorize/ready", "spray_ops.query_filters.collection_statement + production.demand_detail/task_detail + progress",
              extra_resource_types=("task",),
              coverage_description="查看喷油需求、实体库存、工序任务与已确认日报。合格在库、工序量、返工和报废分开；金额与缺料情况尚未接入。"),
    Connector("internal-quote", "内部报价", "implemented_unverified", "get_internal_quote_overview", "internal-quote-collaboration", "quote",
              "读取明确厂区的逻辑报价文档或原版本；detail查看指定resource_id，compare比较resource_id与base_resource_id。金额另需summary_read，未完整核价为未知；HKD采购成本减税不是发票税额，条件不同不直接相减",
              "assistant.quotes.authorize + native summary_read", "internal_quote_queries.documents/detail/summary/comparison",
              coverage_description="查看当前厂区报价文档、原版本与版本比较。金额另需汇总权限；核价不完整或条件不同的版本不直接相减。"),
)


def validate(connectors):
    if len({c.module_id for c in connectors}) != len(connectors):
        raise ValueError("duplicate assistant module")
    active = [c for c in connectors if c.callable]
    if len({c.tool_name for c in active}) != len(active):
        raise ValueError("duplicate assistant tool")
    for connector in active:
        if not all((connector.tool_name, connector.route_name, connector.resource_type,
                    connector.authorize_symbol, connector.domain_reader)):
            raise ValueError("callable assistant connector has incomplete bindings")


validate(CONNECTORS)
BY_MODULE = {c.module_id: c for c in CONNECTORS}
CALLABLE = tuple(c for c in CONNECTORS if c.callable)


def resolve(module_id, resource_type=None):
    # Portal explicitly offers the personal work center. Other module pages
    # must never silently substitute personal tasks for their own business data.
    module_id = "work-center" if module_id == "portal" and resource_type is None else module_id
    connector = BY_MODULE.get(module_id)
    if connector is None or not connector.callable:
        label = connector.label if connector else "当前模块"
        raise AssistantError("module_not_connected", f"{label}尚未接入业务读取；可查看已维护的页面说明。", 422)
    if resource_type is not None and resource_type not in (connector.resource_type, *connector.extra_resource_types):
        raise AssistantError("context_unavailable", "选中记录类型与业务模块不匹配。", 422)
    return connector.tool_name


def coverage():
    return [dict(module_id=c.module_id, label=c.label, coverage_state=c.coverage_state,
                 tools=[c.tool_name] if c.callable else [], read_only=True, reason=c.blocker) for c in CONNECTORS]
